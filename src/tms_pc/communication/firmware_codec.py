"""TMS USB VCP protocol, upstream commit bd60824 (communication.h)."""
from dataclasses import dataclass
import math
import struct
from tms_pc.communication.packet import Packet
from tms_pc.models.enums import Mode, PacketType
from tms_pc.models.status import Status
from tms_pc.models.telemetry import Telemetry
from tms_pc.models.report import HardwareReport
from tms_pc.communication.report_decoder import ReportDecoder, REPORT_PAYLOAD_BYTES

PC_REPORT_PAYLOAD_BYTES = 136
PC_REPORT_FRAME_BYTES = PC_REPORT_PAYLOAD_BYTES + 8
THRUSTER_OFFSET = 60

MODES = (Mode.SAFE, Mode.BOOT, Mode.STANDBY, Mode.CALIBRATION, Mode.MEASUREMENT)
FAULTS = {1: "INIT", 2: "ADC", 4: "SD", 8: "PC_TIMEOUT", 16: "THRUSTER", 32: "DEADLINE", 64: "RX"}


@dataclass(frozen=True)
class FirmwareReport:
    status: Status
    telemetry: Telemetry
    raw: tuple[int, ...]
    valid: bool
    calibrated: int
    battery_voltage: float
    counter: int
    fault: int
    thruster_age_ms: int
    thruster_payload: bytes
    thruster: HardwareReport

    @property
    def fault_text(self) -> str:
        if not self.fault:
            return ""
        names = [name for bit, name in FAULTS.items() if self.fault & bit]
        return f"0x{self.fault:08X}: " + ", ".join(names)


def frame_payload(payload: bytes) -> bytes:
    body = b"AB\x00\x00" + payload
    return body + struct.pack("<I", sum(body) & 0xFFFFFFFF)


def decode_report(payload: bytes) -> FirmwareReport:
    if len(payload) != PC_REPORT_PAYLOAD_BYTES:
        raise ValueError(f"PC report requires {PC_REPORT_PAYLOAD_BYTES} bytes")
    mode, running, acquiring, enabled, thrust = struct.unpack_from("<4Bf", payload)
    if mode >= len(MODES) or any(x not in (0, 1) for x in (running, acquiring, enabled)):
        raise ValueError("Invalid report state")
    if not math.isfinite(thrust) or not 0 <= thrust <= 100:
        raise ValueError("Invalid applied thrust")
    runtime, voltage, current, load, pressure = struct.unpack_from("<d4f", payload, 8)
    if not math.isfinite(runtime) or runtime < 0:
        raise ValueError("Invalid runtime")
    raw = struct.unpack_from("<5H", payload, 32)
    valid, calibrated = struct.unpack_from("<2B", payload, 42)
    if valid not in (0, 1) or calibrated & ~3:
        raise ValueError("Invalid measurement flags")
    battery, counter, fault, age = struct.unpack_from("<f3I", payload, 44)
    # Firmware explicitly emits NaN until calibrated. Never expose unqualified values.
    analog = bool(valid and calibrated & 2)
    voltage, current, pressure, battery = tuple(x if analog and math.isfinite(x) else math.nan for x in (voltage, current, pressure, battery))
    load = load if valid and calibrated & 1 and math.isfinite(load) else math.nan
    status = Status(MODES[mode], bool(running), bool(enabled), thrust, bool(acquiring), math.nan, math.nan)
    telemetry = Telemetry(runtime, voltage, current, load, pressure, float(raw[0]) if valid else math.nan)
    thruster_payload = payload[THRUSTER_OFFSET:THRUSTER_OFFSET + REPORT_PAYLOAD_BYTES]
    thruster = ReportDecoder(byte_order="little").decode(thruster_payload)
    return FirmwareReport(status, telemetry, raw, bool(valid), calibrated, battery, counter, fault, age, thruster_payload, thruster)


class FirmwareCodec:
    """Fixed 144-byte RX frames, 40-byte TX frames; bounded stream recovery."""
    ids = {PacketType.COMMAND_MODE: 1, PacketType.COMMAND_MODE_RUN: 2,
           PacketType.COMMAND_CALIBRATION_ACQUIRE: 3, PacketType.COMMAND_THRUST_ENABLE: 4,
           PacketType.COMMAND_THRUST: 5, PacketType.COMMAND_CALIBRATION_FACTOR: 6,
           PacketType.HEARTBEAT: 7, PacketType.STOP: 8}

    def __init__(self):
        self.buffer = bytearray()
        self.errors: list[str] = []

    def encode(self, packet: Packet) -> bytes:
        payload = bytearray(32)
        payload[0] = self.ids[packet.kind]
        if packet.kind == PacketType.COMMAND_MODE:
            if packet.value == Mode.BOOT:
                raise ValueError("BOOT cannot be requested")
            payload[1] = MODES.index(packet.value)
        elif packet.kind in (PacketType.COMMAND_MODE_RUN, PacketType.COMMAND_CALIBRATION_ACQUIRE, PacketType.COMMAND_THRUST_ENABLE):
            if packet.value not in (False, True):
                raise ValueError("Boolean command required")
            offset = {PacketType.COMMAND_MODE_RUN: 2, PacketType.COMMAND_CALIBRATION_ACQUIRE: 3, PacketType.COMMAND_THRUST_ENABLE: 4}[packet.kind]
            payload[offset] = int(packet.value)
        elif packet.kind == PacketType.COMMAND_THRUST:
            value = float(packet.value)
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Thrust must be 0..100%")
            struct.pack_into("<f", payload, 8, value)
        elif packet.kind == PacketType.COMMAND_CALIBRATION_FACTOR:
            scale, zero = packet.value  # F=(Raw-zero)/scale; slope raw/N, not its reciprocal.
            if not all(math.isfinite(v) for v in (scale, zero)) or not 1e-9 <= abs(scale) <= 1e9 or abs(zero) > 1e6:
                raise ValueError("Calibration exceeds firmware limits")
            struct.pack_into("<2d", payload, 16, scale, zero)
        return frame_payload(payload)

    def feed(self, data: bytes) -> list[Packet]:
        self.buffer.extend(data)
        self.errors.clear()
        result = []
        while True:
            start = self.buffer.find(b"AB\x00\x00")
            if start < 0:
                self.buffer[:] = self.buffer[-3:]
                break
            if start:
                del self.buffer[:start]
            if len(self.buffer) < PC_REPORT_FRAME_BYTES:
                break
            checksum_offset = PC_REPORT_FRAME_BYTES - 4
            body = self.buffer[:checksum_offset]
            checksum = struct.unpack_from("<I", self.buffer, checksum_offset)[0]
            if sum(body) != checksum:
                self.errors.append("Firmware checksum mismatch")
                del self.buffer[0]
                continue
            try:
                report = decode_report(bytes(body[4:]))
            except ValueError as exc:
                self.errors.append(str(exc))
            else:
                result.append(Packet(PacketType.HARDWARE_REPORT, report))
            del self.buffer[:PC_REPORT_FRAME_BYTES]
        return result
