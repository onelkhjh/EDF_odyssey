from dataclasses import replace
import math
import time
import threading
from tms_pc.communication.packet import MockCodec, Packet
from tms_pc.config.settings import Settings
from tms_pc.managers.state_manager import StateManager
from tms_pc.models.enums import Mode, PacketType
from tms_pc.models.status import Status
from tms_pc.models.telemetry import Telemetry


class MockTransport:
    """GUI/communication fixture. Physics do not represent a real EDF."""
    def __init__(self, settings: Settings = Settings()) -> None:
        self.settings = settings
        self.codec = MockCodec()
        self.state = StateManager()
        self.state.observe(Status(mode=Mode.STANDBY))
        self.connected = False
        self.lost = threading.Event()
        self.reference_n = 0.0
        self.runtime = 0.0
        self.measured = 0.0
        self.last_update = self.last_command = time.monotonic()
        self.out = bytearray()

    def connect(self) -> None:
        self.connected = self.state.connected = True
        self.lost.clear()
        self.state.observe(Status(mode=Mode.STANDBY))
        self.runtime = self.measured = 0.0
        self.last_update = self.last_command = time.monotonic()
        self.out.clear()
        self._status()

    def disconnect(self) -> None:
        self.connected = self.state.connected = False
        self.state.observe(replace(self.state.status, mode=Mode.SAFE, mode_run=False, thrust_enable=False, thrust_command=0, acquire=False))

    def _status(self) -> None:
        self.out.extend(self.codec.encode(Packet(PacketType.STATUS, self.state.status)))

    def send(self, data: bytes) -> None:
        if not self.connected:
            raise ConnectionError("Mock disconnected")
        if self.lost.is_set():
            return
        for packet in self.codec.feed(data):
            try:
                self.state.guard(packet.kind, packet.value)
                s, value = self.state.status, packet.value
                fields: dict = {}
                if packet.kind == PacketType.COMMAND_MODE:
                    fields = {"mode": value, "mode_run": False, "thrust_enable": False, "thrust_command": 0.0, "acquire": False}
                elif packet.kind == PacketType.COMMAND_MODE_RUN:
                    fields = {"mode_run": value}
                elif packet.kind == PacketType.COMMAND_THRUST_ENABLE:
                    fields = {"thrust_enable": value}
                    if not value:
                        fields["thrust_command"] = 0.0
                elif packet.kind == PacketType.COMMAND_THRUST:
                    fields = {"thrust_command": value}
                elif packet.kind == PacketType.COMMAND_CALIBRATION_ACQUIRE:
                    fields = {"acquire": value}
                elif packet.kind == PacketType.COMMAND_CALIBRATION_FACTOR:
                    fields = {"slope": value[0], "offset": value[1]}
                else:
                    raise ValueError("Not a command")
                self.state.observe(replace(s, **fields))
                self.last_command = time.monotonic()
                self._status()
            except ValueError as exc:
                self.out.extend(self.codec.encode(Packet(PacketType.FAULT, str(exc))))

    def read(self) -> bytes:
        if not self.connected:
            raise ConnectionError("Mock disconnected")
        now = time.monotonic()
        if now - self.last_command > self.settings.mock_watchdog_s and self.state.status.thrust_enable:
            self.state.observe(replace(self.state.status, mode=Mode.SAFE, mode_run=False, thrust_enable=False, thrust_command=0.0))
        dt = now - self.last_update
        if dt >= self.settings.mock_period_s:
            self.last_update = now
            self.runtime += dt
            s = self.state.status
            target = s.thrust_command * 0.2 if s.thrust_enable and s.mode_run else 0.0
            self.measured += (target - self.measured) * (1 - math.exp(-dt / 0.3))
            raw_force = self.reference_n if s.mode == Mode.CALIBRATION else self.measured
            # Raw transducer characteristic remains fixed when calibration factors change.
            raw = 1000.0 * raw_force + 100.0 + math.sin(self.runtime * 7)
            telemetry = Telemetry(self.runtime, 24 - target * 0.06 + 0.03 * math.sin(self.runtime), 0.2 + target * 1.4, (raw - s.offset) / s.slope, 101.3 - target * 0.04, raw)
            if not self.lost.is_set():
                self._status()
                self.out.extend(self.codec.encode(Packet(PacketType.TELEMETRY, telemetry)))
        if self.lost.is_set():
            self.out.clear()
            return b""
        data = bytes(self.out)
        self.out.clear()
        return data
