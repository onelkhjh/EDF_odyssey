from dataclasses import dataclass
import math
import struct
from tms_pc.communication.crc import MockCRC32
from tms_pc.models.enums import Mode, PacketType
from tms_pc.models.status import Status
from tms_pc.models.telemetry import Telemetry


@dataclass(frozen=True)
class Packet:
    kind: PacketType
    value: object


class MockCodec:
    """Simulator-only packed schema. Never use as a hardware default."""
    sof = b"TM"
    formats = {
        PacketType.COMMAND_MODE: "B", PacketType.COMMAND_MODE_RUN: "B",
        PacketType.COMMAND_CALIBRATION_ACQUIRE: "B", PacketType.COMMAND_THRUST_ENABLE: "B",
        PacketType.COMMAND_THRUST: "f", PacketType.COMMAND_CALIBRATION_FACTOR: "dd",
        PacketType.STATUS: "BBBfBdd", PacketType.TELEMETRY: "dffffd",
    }

    def __init__(self, max_payload: int = 512) -> None:
        self.buffer = bytearray()
        self.max_payload = max_payload
        self.crc = MockCRC32()
        self.errors: list[str] = []

    def encode(self, packet: Packet) -> bytes:
        kind, value = packet.kind, packet.value
        if kind == PacketType.FAULT:
            payload = str(value).encode("utf-8")
        else:
            if kind == PacketType.STATUS:
                args = (value.mode.value, value.mode_run, value.thrust_enable, value.thrust_command, value.acquire, value.slope, value.offset)
            elif kind == PacketType.TELEMETRY:
                args = (value.runtime, value.motor_voltage, value.motor_current, value.load_cell, value.pressure, value.raw_load_cell)
            elif kind == PacketType.COMMAND_MODE:
                args = (value.value,)
            elif kind == PacketType.COMMAND_CALIBRATION_FACTOR:
                args = tuple(value)
            else:
                args = (value,)
            payload = struct.pack("<" + self.formats[kind], *args)
        if len(payload) > self.max_payload:
            raise ValueError("Packet exceeds payload limit")
        body = struct.pack("<BH", kind.value, len(payload)) + payload
        return self.sof + body + struct.pack("<I", self.crc.calculate(body))

    def decode_payload(self, kind: PacketType, payload: bytes) -> object:
        if kind == PacketType.FAULT:
            return payload.decode("utf-8")
        values = struct.unpack("<" + self.formats[kind], payload)
        if not all(math.isfinite(x) for x in values):
            raise ValueError("Non-finite packet field")
        if kind == PacketType.STATUS:
            if any(values[i] not in (0, 1) for i in (1, 2, 4)) or not 0 <= values[3] <= 100 or values[5] == 0:
                raise ValueError("Invalid status domain")
            return Status(Mode(values[0]), bool(values[1]), bool(values[2]), values[3], bool(values[4]), values[5], values[6])
        if kind == PacketType.TELEMETRY:
            if values[0] < 0:
                raise ValueError("Negative runtime")
            return Telemetry(*values)
        if kind == PacketType.COMMAND_MODE:
            return Mode(values[0])
        if kind in (PacketType.COMMAND_MODE_RUN, PacketType.COMMAND_THRUST_ENABLE, PacketType.COMMAND_CALIBRATION_ACQUIRE):
            if values[0] not in (0, 1):
                raise ValueError("Invalid boolean")
            return bool(values[0])
        if kind == PacketType.COMMAND_CALIBRATION_FACTOR:
            return values
        if not 0 <= values[0] <= 100:
            raise ValueError("Invalid thrust range")
        return values[0]

    def feed(self, data: bytes) -> list[Packet]:
        self.buffer.extend(data)
        result: list[Packet] = []
        self.errors.clear()
        while len(self.buffer) >= 5:
            if self.buffer[:2] != self.sof:
                del self.buffer[0]
                continue
            ident, length = struct.unpack("<BH", self.buffer[2:5])
            if length > self.max_payload:
                self.errors.append("Invalid packet length")
                del self.buffer[0]
                continue
            try:
                kind = PacketType(ident)
                if kind != PacketType.FAULT and length != struct.calcsize("<" + self.formats[kind]):
                    raise ValueError("Invalid payload length")
            except (ValueError, KeyError) as exc:
                self.errors.append(str(exc))
                del self.buffer[0]
                continue
            size = 9 + length
            if len(self.buffer) < size:
                break
            body = bytes(self.buffer[2:5 + length])
            checksum = struct.unpack("<I", self.buffer[5 + length:size])[0]
            if checksum != self.crc.calculate(body):
                self.errors.append("Corrupted mock CRC")
                del self.buffer[0]
                continue
            payload = bytes(self.buffer[5:5 + length])
            del self.buffer[:size]
            try:
                result.append(Packet(kind, self.decode_payload(kind, payload)))
            except (ValueError, struct.error, UnicodeError) as exc:
                self.errors.append(str(exc))
        return result
