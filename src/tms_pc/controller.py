from dataclasses import dataclass
import logging
import math
import time
from PySide6.QtCore import QObject, Signal, Slot, Qt, QTimer
from tms_pc.communication.mock_transport import MockTransport
from tms_pc.communication.packet import Packet
from tms_pc.config.settings import Settings
from tms_pc.managers.communication_manager import CommunicationManager
from tms_pc.managers.state_manager import StateManager
from tms_pc.managers.calibration_manager import CalibrationManager
from tms_pc.managers.measurement_manager import MeasurementManager
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
        self.visualization = VisualizationManager(settings.buffer_samples)
        self.communication = CommunicationManager(settings)
        self.communication.packet_received.connect(self._session_packet, Qt.ConnectionType.QueuedConnection)
        self.communication.connection.connect(self._session_connection, Qt.ConnectionType.QueuedConnection)
        self.communication.sent.connect(self._session_sent, Qt.ConnectionType.QueuedConnection)
        self.communication.warning.connect(self._session_warning, Qt.ConnectionType.QueuedConnection)
        self.telemetry: Telemetry | None = None
        self.pending: dict[int, Expectation] = {}
        self.commanded = 0.0
        self.message = "DISCONNECTED"
        self.fault = ""
        self.stop_steps: list[Packet] = []
        self.stopping = False
        self.emergency = False
        self.transport: MockTransport | None = None
        self.last_thrust_sent = 0.0
        self.accept_packets = False
        self.reconnect_requested = False
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
        raise ValueError("Hardware protocol TBD: real Serial operation is blocked until a reviewed adapter is supplied")

    def _warn(self, message: str) -> None:
        self.message = message
        log.warning(message)
        self.warning.emit(message)
        self.changed.emit()

    def _connection(self, connected: bool, message: str) -> None:
        # Transport connect is not valid STATUS feedback.
        if not connected:
            self.accept_packets = False
            self.state.connected = False
            self.pending.clear()
            self.measurement.reset()
            self.stop_steps.clear()
            self.stopping = False
            self.commanded = 0.0
            self.telemetry = None
            self.visualization.samples.clear()
        if message != "DISCONNECTED" or "LOST" not in self.message:
            self.message = message
        log.info("Connection %s", message)
        self.changed.emit()

    def _sent(self, token: int, sent_at: float) -> None:
        if token in self.pending:
            self.pending[token].sent_at = sent_at

    def request(self, kind: PacketType, value: object) -> None:
        if self.stopping or self.pending:
            raise ValueError("Waiting for command feedback; Stop remains available")
        self.state.guard(kind, value)
        if kind == PacketType.COMMAND_MODE_RUN and value:
            self.measurement.reset()
        self._send(Packet(kind, value))

    def _send(self, packet: Packet, priority: int = 10) -> None:
        mapping = {
            PacketType.COMMAND_MODE: "mode", PacketType.COMMAND_MODE_RUN: "mode_run",
            PacketType.COMMAND_THRUST_ENABLE: "thrust_enable", PacketType.COMMAND_THRUST: "thrust_command",
            PacketType.COMMAND_CALIBRATION_ACQUIRE: "acquire", PacketType.COMMAND_CALIBRATION_FACTOR: "factors",
        }
        token = self.communication.submit(packet, priority)
        self.pending[token] = Expectation(mapping[packet.kind], packet.value, time.monotonic())
        if packet.kind == PacketType.COMMAND_THRUST:
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
        self.stop_steps = []
        if self.state.status.mode == Mode.MEASUREMENT:
            self.stop_steps.append(Packet(PacketType.COMMAND_THRUST, 0.0))
        self.stop_steps.extend([Packet(PacketType.COMMAND_THRUST_ENABLE, False), Packet(PacketType.COMMAND_MODE_RUN, False)])
        if self.state.status.acquire:
            self.stop_steps.append(Packet(PacketType.COMMAND_CALIBRATION_ACQUIRE, False))
        if emergency:
            self.stop_steps.append(Packet(PacketType.COMMAND_MODE, Mode.SAFE))
        log.info("Measurement Stop / Emergency=%s", emergency)
        self._next_stop()

    def _next_stop(self) -> None:
        if self.stop_steps and self.state.connected:
            self._send(self.stop_steps.pop(0), priority=0)
        else:
            self.stopping = False
            self.changed.emit()

    def _matches(self, expected: Expectation) -> bool:
        s = self.state.status
        if expected.field == "factors":
            return math.isclose(s.slope, expected.value[0], rel_tol=1e-8) and math.isclose(s.offset, expected.value[1], abs_tol=1e-8)
        observed = getattr(s, expected.field)
        if expected.field == "thrust_command":
            return abs(observed - expected.value) <= self.settings.thrust_tolerance
        return observed == expected.value

    def _packet(self, packet: Packet) -> None:
        if not self.accept_packets:
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
                elif not self.fault:
                    self.message = "CONNECTED / FEEDBACK CONFIRMED"
            if self.state.status.mode_run and not self.stopping and not self.pending and abs(self.commanded - self.state.status.thrust_command) > self.settings.thrust_tolerance:
                self._warn("COMMAND / TMS STATE MISMATCH")
        elif packet.kind == PacketType.TELEMETRY:
            self.telemetry = packet.value
            self.visualization.append(packet.value, self.state.status.thrust_command)
            if self.state.status.acquire:
                if len(self.calibration.samples) < self.settings.calibration_max_samples:
                    self.calibration.samples.append(packet.value.raw_load_cell)
                elif not self.pending:
                    self._warn("Calibration sample limit reached; acquisition stop requested")
                    self.request(PacketType.COMMAND_CALIBRATION_ACQUIRE, False)
            if self.state.status.mode_run and self.measurement.use_profile and not self.stopping:
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
        self.changed.emit()

    def _tick(self) -> None:
        if self.reconnect_requested and not self.communication.thread.is_alive():
            self.connect_mock()
        now = time.monotonic()
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
        self.message = "DISCONNECTED / THRUST COMMAND DISABLED"
        self.changed.emit()
