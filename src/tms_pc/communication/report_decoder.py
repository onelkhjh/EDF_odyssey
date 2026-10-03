import math
import struct
from typing import Literal
from tms_pc.models.report import HardwareReport

REPORT_PAYLOAD_BYTES = 64
REPORT_STRUCT_FORMAT = "Id12fB3s"


class ReportDecoder:
    """Decode an already-framed report_t; framing/CRC are not specified yet.

    Firmware must confirm IEEE-754 binary32/binary64 and byte order.
    Units/status bits are intentionally not inferred.
    """

    def __init__(self, *, byte_order: Literal["little", "big"]) -> None:
        prefixes = {"little": "<", "big": ">"}
        if byte_order not in prefixes:
            raise ValueError("Explicit little or big byte order is required")
        self.layout = struct.Struct(prefixes[byte_order] + REPORT_STRUCT_FORMAT)
        if self.layout.size != REPORT_PAYLOAD_BYTES:
            raise ValueError("Unexpected report_t layout size")

    def decode(self, payload: bytes) -> HardwareReport:
        if len(payload) != REPORT_PAYLOAD_BYTES:
            raise ValueError(f"report_t requires exactly 64 bytes; received {len(payload)}")
        values = self.layout.unpack(payload)
        if not all(math.isfinite(number) for number in values[1:14]):
            raise ValueError("report_t contains non-finite sensor/time values")
        return HardwareReport(
            packet_counter=values[0], ref_time=values[1], thrust=values[2],
            deg=tuple(values[3:7]), voltage_edf=values[7], current_edf=values[8],
            deg_m=tuple(values[9:13]), logic_voltage=values[13],
            subsystem_status=values[14], padding=values[15],
        )
