from dataclasses import dataclass
import logging
import math
import time
from PySide6.QtCore import QObject, Signal, Slot, Qt, QTimer
from tms_pc.communication.mock_transport import MockTransport
from tms_pc.communication.serial_transport import SerialTransport
from tms_pc.communication.firmware_codec import FirmwareCodec
from tms_pc.communication.packet import Packet
from tms_pc.config.settings import Settings
from tms_pc.managers.communication_manager import CommunicationManager
from tms_pc.managers.state_manager import StateManager
from tms_pc.managers.calibration_manager import CalibrationManager
from tms_pc.managers.measurement_manager import MeasurementManager
from tms_pc.managers.measurement_recorder import MeasurementRecorder
from tms_pc.managers.visualization_manager import VisualizationManager
from tms_pc.models.enums import Mode, PacketType
from tms_pc.models.telemetry import Telemetry

log = logging.getLogger(__name__)


@dataclass
class Expectation:
    field: str
    value: object
    queued_at: float
    sent_at: float | None = None


class TMSController(QObject):
    changed = Signal()
    warning = Signal(str)

    def __init__(self, settings: Settings = Settings()) -> None:
        super().__init__()
        self.settings = settings
        self.state = StateManager()
        self.calibration = CalibrationManager()
        self.measurement = MeasurementManager()
        self.recorder = MeasurementRecorder()
        self.visualization = VisualizationManager(settings.buffer_samples)
        self.communication = CommunicationManager(settings)
        self.communication.packet_received.connect(self._session_packet, Qt.ConnectionType.QueuedConnection)
        self.communication.connection.connect(self._session_connection, Qt.ConnectionType.QueuedConnection)
        self.communication.sent.connect(self._session_sent, Qt.ConnectionType.QueuedConnection)
        self.communication.warning.connect(self._session_warning, Qt.ConnectionType.QueuedConnection)
        self.telemetry: Telemetry | None = None
        self.pending: dict[int, Expectation] = {}
        self.commanded = 0.0
        self.throttle_tx = "Throttle TX: no command sent"
        self.throttle_tokens = {}
        self.message = "DISCONNECTED"
        self.fault = ""
        self.stop_steps: list[Packet] = []
        self.stopping = False
        self.emergency = False
        self.transport: MockTransport | None = None
        self.last_thrust_sent = 0.0
        self.accept_packets = False
        self.reconnect_requested = False
        self.hardware = False
        self.hardware_report = None
        self.last_status_at = 0.0
        self.calibration_start_requested = False
        self.calibration_stop_requested = False
        self.calibration_exit_mode = None
        self.hardware_status_lost = False
        self.processing_report = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(20)

    def connect_mock(self) -> None:
        if self.communication.thread and self.communication.thread.is_alive():
            if self.communication.stop_event.is_set():
                self.reconnect_requested = True
                self.message = "RECONNECTING — waiting for previous connection to close"
                self.changed.emit()
                return
            raise ValueError("Disconnect first")
        self.reconnect_requested = False
        self.hardware = False
        self.hardware_report = None
        self.transport = MockTransport(self.settings)
        self.visualization.samples.clear()
        self.telemetry = None
        self.fault = ""
        self.state = StateManager()
        self.measurement.reset()
        self.commanded = 0.0
        self.message = "CONNECTING — awaiting telemetry"
        self.accept_packets = True
        self.communication.connect_transport(self.transport)
        self.changed.emit()

    @Slot(int, object)
    def _session_packet(self, session: int, packet: Packet) -> None:
        if session == self.communication.session:
            self._packet(packet)

    @Slot(int, bool, str)
    def _session_connection(self, session: int, connected: bool, message: str) -> None:
        if session == self.communication.session:
            self._connection(connected, message)

    @Slot(int, int, float)
    def _session_sent(self, session: int, token: int, sent_at: float) -> None:
        if session == self.communication.session:
            self._sent(token, sent_at)

    @Slot(int, str)
    def _session_warning(self, session: int, message: str) -> None:
        if session == self.communication.session:
            self._warn(message)

    def connect_serial(self, port: str, baud: int) -> None:
        self.calibration_stop_requested = False
        self.calibration_exit_mode = None
        if self.communication.thread and self.communication.thread.is_alive():
            raise ValueError("Disconnect first")
        if not 0 < self.settings.hardware_heartbeat_s < 0.5:
            raise ValueError("Firmware heartbeat interval must be below 500 ms")
        if not 0 < self.settings.hardware_status_timeout_s < 0.5:
            raise ValueError("STATUS timeout must be below 500 ms")
        transport = SerialTransport(port, baud, self.settings)
        self.hardware = True
        self.hardware_report = None
        self.last_status_at = 0.0
        self.calibration_start_requested = False
        self.hardware_status_lost = False
        self.transport = None
        self.telemetry = None
        self.visualization.samples.clear()
        self.state = StateManager()
        self.measurement.reset()
        self.pending.clear()
        self.fault = ""
        self.commanded = 0.0
        self.message = "CONNECTING / TMS USB VCP (136-byte report)"
        self.accept_packets = True
        self.communication.connect_transport(transport, FirmwareCodec())
        self.changed.emit()

    def _warn(self, message: str) -> None:
        self.message = message
        log.warning(message)
        self.warning.emit(message)
        self.changed.emit()

    def _connection(self, connected: bool, message: str) -> None:
        # Transport connect is not valid STATUS feedback.
        if not connected:
            self.recorder.finish()
            self.accept_packets = False
            self.state.connected = False
            self.pending.clear()
            self.measurement.reset()
            self.stop_steps.clear()
            self.stopping = False
            self.commanded = 0.0
            self.telemetry = None
            self.visualization.samples.clear()
            self.hardware_report = None
            self.calibration_start_requested = False
        if message != "DISCONNECTED" or "LOST" not in self.message:
            self.message = message
        log.info("Connection %s", message)
        self.changed.emit()

    def _sent(self, token: int, sent_at: float) -> None:
        if token in self.throttle_tokens:
            value = self.throttle_tokens.pop(token)
            self.throttle_tx = f"Throttle {value:.2f}%: COM WRITE COMPLETE / check TMS Applied"
            log.info(self.throttle_tx)
            self.changed.emit()
        if token in self.pending:
            self.pending[token].sent_at = sent_at

    def request(self, kind: PacketType, value: object) -> None:
        if self.stopping or self.pending:
            raise ValueError("Waiting for command feedback; Stop remains available")
        self.state.guard(kind, value)
        if self.hardware:
            if self.hardware_status_lost or (time.monotonic() - self.last_status_at > self.settings.hardware_status_timeout_s and not (kind == PacketType.COMMAND_MODE and value == Mode.SAFE)):
                raise ValueError("Stale firmware STATUS; reconnect before operating")
            if kind != PacketType.COMMAND_MODE and self.fault:
                raise ValueError("Firmware fault or stale STATUS; Stop or explicit mode recovery required")
            if kind == PacketType.COMMAND_CALIBRATION_FACTOR:
                raise ValueError("Firmware report has no coefficient echo/ACK; Apply is unavailable until verified feedback is added")
            if kind == PacketType.COMMAND_MODE_RUN and value and self.state.status.mode == Mode.MEASUREMENT:
                if self.hardware_report is None or self.hardware_report.thruster_age_ms > 500:
                    raise ValueError("Start requires fresh thruster report (age <= 500 ms)")
            if kind == PacketType.COMMAND_CALIBRATION_ACQUIRE and value and not self.state.status.mode_run:
                self.calibration_start_requested = True
                self._send(Packet(PacketType.COMMAND_MODE_RUN, True))
                return
        if kind == PacketType.COMMAND_MODE_RUN and value:
            if self.state.status.mode == Mode.MEASUREMENT:
                self.recorder.begin(self.hardware)
            self.measurement.reset()
        self._send(Packet(kind, value))

    def stop_acquire(self) -> None:
        if self.hardware and self.state.status.mode == Mode.CALIBRATION and not self.state.status.acquire:
            self.request(PacketType.COMMAND_MODE_RUN, False)
            return
        self.request(PacketType.COMMAND_CALIBRATION_ACQUIRE, False)
        self.calibration_stop_requested = self.hardware

    def change_mode(self, mode: Mode) -> None:
        status = self.state.status
        if self.hardware and status.mode == Mode.CALIBRATION and (status.mode_run or status.acquire) and mode != Mode.SAFE:
            if mode == Mode.BOOT:
                raise ValueError("BOOT cannot be requested")
            self.stop_acquire()
            self.calibration_exit_mode = mode
            return
        self.request(PacketType.COMMAND_MODE, mode)

    def send_throttle(self, value: float) -> None:
        value = float(value)
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError("Throttle must be finite and 0..100%")
        if not self.hardware:
            self.request(PacketType.COMMAND_THRUST, value)
            return
        if not self.state.connected or self.stopping or self.hardware_status_lost:
            raise ValueError("Connect and recover the TMS link before sending throttle")
        if self.pending:
            raise ValueError("Wait for the current command feedback before sending throttle")
        status = self.state.status
        if status.mode == Mode.MEASUREMENT and status.mode_run and status.thrust_enable and not self.fault:
            self.request(PacketType.COMMAND_THRUST, value)
            return
        # An explicit transmission probe does not Enable, Start, or claim application.
        token = self.communication.submit(Packet(PacketType.COMMAND_THRUST, value))
        self.throttle_tokens[token] = value
        self.throttle_tx = f"Throttle {value:.2f}%: QUEUED / APPLICATION UNCONFIRMED"
        self.message = f"Throttle {value:.2f}% TX REQUESTED / APPLICATION UNCONFIRMED; firmware requires Enable + Start"
        log.info(self.message)
        self.changed.emit()

    def _send(self, packet: Packet, priority: int = 10) -> None:
        mapping = {
            PacketType.COMMAND_MODE: "mode", PacketType.COMMAND_MODE_RUN: "mode_run",
            PacketType.COMMAND_THRUST_ENABLE: "thrust_enable", PacketType.COMMAND_THRUST: "thrust_command",
            PacketType.COMMAND_CALIBRATION_ACQUIRE: "acquire", PacketType.COMMAND_CALIBRATION_FACTOR: "factors",
        }
        token = self.communication.submit(packet, priority)
        self.pending[token] = Expectation(mapping[packet.kind], packet.value, time.monotonic())
        if packet.kind == PacketType.COMMAND_THRUST:
            self.throttle_tokens[token] = float(packet.value)
            self.throttle_tx = f"Throttle {float(packet.value):.2f}%: QUEUED"
            self.commanded = float(packet.value)
            self.last_thrust_sent = time.monotonic()
        self.changed.emit()

    def stop(self, emergency: bool = False) -> None:
        if not self.state.connected:
            raise ValueError("Connection lost: final stop must be performed independently by TMS")
        self.communication.clear_queue()
        self.pending.clear()
        self.measurement.reset()
        self.stopping = True
        self.emergency = emergency
        self.calibration_start_requested = False
        self.stop_steps = []
        self.calibration_stop_requested = False
        self.calibration_exit_mode = None
        if self.hardware:
            # Firmware id=8 atomically zeros/disables/stops and enters Standby.
            # SAFE mode command performs the same shutdown and enters Safe.
            if emergency:
                self._send(Packet(PacketType.COMMAND_MODE, Mode.SAFE), priority=0)
            else:
                self._send_hardware_stop()
            return
        if self.state.status.mode == Mode.MEASUREMENT:
            self.stop_steps.append(Packet(PacketType.COMMAND_THRUST, 0.0))
        self.stop_steps.extend([Packet(PacketType.COMMAND_THRUST_ENABLE, False), Packet(PacketType.COMMAND_MODE_RUN, False)])
        if self.state.status.acquire:
            self.stop_steps.append(Packet(PacketType.COMMAND_CALIBRATION_ACQUIRE, False))
        if emergency:
            self.stop_steps.append(Packet(PacketType.COMMAND_MODE, Mode.SAFE))
        log.info("Measurement Stop / Emergency=%s", emergency)
        self._next_stop()

    def _send_hardware_stop(self) -> None:
        token = self.communication.submit(Packet(PacketType.STOP, None), priority=0)
        self.pending[token] = Expectation("stopped", Mode.STANDBY, time.monotonic())
        self.changed.emit()

    def _next_stop(self) -> None:
        if self.stop_steps and self.state.connected:
            self._send(self.stop_steps.pop(0), priority=0)
        else:
            self.stopping = False
            self.changed.emit()

    def _matches(self, expected: Expectation) -> bool:
        s = self.state.status
        if expected.field == "stopped" or (self.hardware and self.stopping and expected.field == "mode"):
            return s.mode == expected.value and not s.mode_run and not s.thrust_enable and not s.acquire and abs(s.thrust_command) <= self.settings.thrust_tolerance
        if expected.field == "factors":
            return math.isclose(s.slope, expected.value[0], rel_tol=1e-8) and math.isclose(s.offset, expected.value[1], abs_tol=1e-8)
        observed = getattr(s, expected.field)
        if expected.field == "thrust_command":
            return abs(observed - expected.value) <= self.settings.thrust_tolerance
        return observed == expected.value

    def _packet(self, packet: Packet) -> None:
        if not self.accept_packets:
            return
        if packet.kind == PacketType.HARDWARE_REPORT:
            report = packet.value
            previous_fault = self.fault
            self.hardware_report = report
            self.last_status_at = time.monotonic()
            self.fault = report.fault_text
            # Fault arrives before STATUS processing, so profiles cannot continue on it.
            if report.fault:
                self.measurement.reset()
                self.measurement.use_profile = False
                self.calibration_start_requested = False
            self.processing_report = True
            try:
                self._packet(Packet(PacketType.STATUS, report.status))
                self._packet(Packet(PacketType.TELEMETRY, report.telemetry))
            finally:
                self.processing_report = False
            if report.fault and self.fault != previous_fault:
                self._warn("TMS FAULT: " + self.fault)
            self.changed.emit()
            return
        if packet.kind == PacketType.STATUS:
            self.state.connected = True
            self.state.observe(packet.value)
            for token, expected in list(self.pending.items()):
                if expected.sent_at is not None and self._matches(expected):
                    log.info("Feedback %s = %s", expected.field, expected.value)
                    del self.pending[token]
            if not self.pending:
                if self.stopping:
                    self._next_stop()
                elif not self.fault and not self.hardware_status_lost:
                    self.message = "CONNECTED / FEEDBACK CONFIRMED"
            if self.hardware and self.calibration_start_requested and not self.pending and not self.stopping:
                self.calibration_start_requested = False
                if self.state.status.mode == Mode.CALIBRATION and self.state.status.mode_run and not self.fault:
                    self.request(PacketType.COMMAND_CALIBRATION_ACQUIRE, True)
            if self.calibration_stop_requested and not self.pending and not self.stopping:
                self.calibration_stop_requested = False
                if self.hardware and self.state.status.mode == Mode.CALIBRATION and not self.state.status.acquire and self.state.status.mode_run and not self.fault:
                    self.request(PacketType.COMMAND_MODE_RUN, False)
            if self.calibration_exit_mode is not None and not self.pending and not self.stopping:
                status = self.state.status
                if not status.mode_run and not status.acquire and not status.thrust_enable:
                    target = self.calibration_exit_mode
                    self.calibration_exit_mode = None
                    self.request(PacketType.COMMAND_MODE, target)
            if self.state.status.mode_run and not self.stopping and not self.pending and abs(self.commanded - self.state.status.thrust_command) > self.settings.thrust_tolerance:
                self._warn("COMMAND / TMS STATE MISMATCH")
        elif packet.kind == PacketType.TELEMETRY:
            self.telemetry = packet.value
            self.recorder.append(packet.value, self.state.status, self.commanded, self.fault)
            if self.recorder.stream is not None and not self.pending and not self.state.status.mode_run:
                self.recorder.finish()
            self.visualization.append(packet.value, self.state.status.thrust_command,
                                      time.monotonic() if self.hardware else None)
            if self.state.status.acquire and math.isfinite(packet.value.raw_load_cell):
                if len(self.calibration.samples) < self.settings.calibration_max_samples:
                    self.calibration.samples.append(packet.value.raw_load_cell)
                elif not self.pending:
                    self._warn("Calibration sample limit reached; acquisition stop requested")
                    self.request(PacketType.COMMAND_CALIBRATION_ACQUIRE, False)
            if self.state.status.mode_run and self.measurement.use_profile and not self.stopping and not self.fault:
                try:
                    command, done = self.measurement.command(packet.value.runtime)
                    if done:
                        self.stop()
                    elif not self.pending:
                        self.request(PacketType.COMMAND_THRUST, command)
                except ValueError as exc:
                    self._warn(str(exc))
                    self.stop()
        elif packet.kind == PacketType.FAULT:
            self.fault = str(packet.value)
            self._warn("TMS FAULT: " + self.fault)
        if not self.processing_report:
            self.changed.emit()

    def _tick(self) -> None:
        if self.reconnect_requested and not self.communication.thread.is_alive():
            self.connect_mock()
        now = time.monotonic()
        received_at = max(self.last_status_at, self.communication.last_report_at)
        if self.hardware and self.state.connected and not self.hardware_status_lost and now - received_at > self.settings.hardware_status_timeout_s:
            self.hardware_status_lost = True
            self._warn("TMS STATUS TIMEOUT / STOP REQUESTED, NOT CONFIRMED")
            if not self.stopping:
                self.stop(emergency=True)
            return
        if self.hardware_status_lost and not self.stopping:
            # Keep receiving after a brief gap. Operation stays latched off until reconnect.
            self.message = "TMS STATUS TIMEOUT / MONITORING ONLY; RECONNECT BEFORE OPERATING"
        expired = [token for token, item in self.pending.items() if now - (item.sent_at or item.queued_at) > self.settings.feedback_timeout_s]
        if expired:
            for token in expired:
                del self.pending[token]
            self._warn("COMMAND FEEDBACK TIMEOUT / COMMAND-TMS STATE MISMATCH")
            if self.stopping:
                self._next_stop()
            elif self.state.connected:
                # A failed dangerous command invalidates operation; request a bounded Stop.
                self.stop(emergency=True)
        elif (self.transport is not None and self.state.connected
              and self.state.status.mode_run and self.state.status.thrust_enable
              and not self.stopping and not self.pending
              and not self.measurement.use_profile
              and now - self.last_thrust_sent >= self.settings.mock_command_refresh_s):
            # Simulator-only watchdog renewal. Real firmware heartbeat policy remains TBD.
            self.request(PacketType.COMMAND_THRUST, self.commanded)

    def disconnect(self) -> None:
        self.recorder.finish()
        self.throttle_tokens.clear()
        self.throttle_tx = "Throttle TX: disconnected"
        self.calibration_stop_requested = False
        self.calibration_exit_mode = None
        self.reconnect_requested = False
        self.accept_packets = False
        self.communication.disconnect()
        self.state.connected = False
        self.pending.clear()
        self.measurement.reset()
        self.commanded = 0.0
        self.telemetry = None
        self.visualization.samples.clear()
        self.stopping = False
        self.stop_steps.clear()
        self.hardware_report = None
        self.calibration_start_requested = False
        self.message = "DISCONNECTED / THRUST COMMAND DISABLED"
        self.changed.emit()
