import math
import struct
from typing import Literal
from tms_pc.models.report import HardwareReport

REPORT_PAYLOAD_BYTES = 72
REPORT_STRUCT_FORMAT = "Id13fB7s"


class ReportDecoder:
    """Decode bd60824's packed thruster report; match firmware validity checks."""

    def __init__(self, *, byte_order: Literal["little", "big"]) -> None:
        prefixes = {"little": "<", "big": ">"}
        if byte_order not in prefixes:
            raise ValueError("Explicit little or big byte order is required")
        self.layout = struct.Struct(prefixes[byte_order] + REPORT_STRUCT_FORMAT)
        if self.layout.size != REPORT_PAYLOAD_BYTES:
            raise ValueError("Unexpected report_t layout size")

    def decode(self, payload: bytes) -> HardwareReport:
        if len(payload) != REPORT_PAYLOAD_BYTES:
            raise ValueError(f"report_t requires exactly {REPORT_PAYLOAD_BYTES} bytes; received {len(payload)}")
        values = self.layout.unpack(payload)
        if not all(math.isfinite(number) for number in values[1:15]):
            raise ValueError("report_t contains non-finite sensor/time values")
        if values[1] < 0:
            raise ValueError("report_t contains negative ref_time")
        if any(values[16]):
            raise ValueError("report_t padding must be zero")
        return HardwareReport(
            packet_counter=values[0], ref_time=values[1], thrust=values[2],
            deg=tuple(values[3:7]), voltage_edf=values[7], current_edf=values[8],
            deg_m=tuple(values[9:13]), logic_voltage=values[13],
            battery_percent=values[14], subsystem_status=values[15], padding=values[16],
        )
