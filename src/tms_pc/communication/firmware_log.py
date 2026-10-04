"""Read firmware DATAxxxx.BIN 512-byte sectors without loading preallocated tail.

CLI: python -m tms_pc.communication.firmware_log DATA0000.BIN output.csv
CSV retains firmware pressure units; it is not the canonical analysis format.
"""
import argparse
import csv
from pathlib import Path
import struct
from tms_pc.communication.firmware_codec import decode_report, PC_REPORT_PAYLOAD_BYTES

SD_CHECKSUM_OFFSET = 4 + 8 + PC_REPORT_PAYLOAD_BYTES


def iter_records(path):
    previous_counter = None
    previous_time = None
    with Path(path).open("rb") as source:
        sector_index = 0
        while sector := source.read(512):
            if len(sector) != 512:
                raise ValueError(f"Partial sector {sector_index}")
            if not any(sector):
                return  # preallocated unwritten tail
            if sector[:4] != b"AB\x00\x00" or sum(sector[:SD_CHECKSUM_OFFSET]) != struct.unpack_from("<I", sector, SD_CHECKSUM_OFFSET)[0]:
                raise ValueError(f"Invalid header/checksum at sector {sector_index}")
            counter = struct.unpack_from("<I", sector, 4)[0]
            report = decode_report(sector[12:SD_CHECKSUM_OFFSET])
            if previous_counter is not None:
                delta = (counter - previous_counter) & 0xFFFFFFFF
                if delta == 0 or delta >= 0x80000000:
                    raise ValueError(f"Non-increasing record counter at sector {sector_index}")
            else:
                delta = 1
            if previous_time is not None and report.telemetry.runtime < previous_time:
                raise ValueError(f"Runtime regression at sector {sector_index}")
            yield sector_index, counter, delta - 1, report
            previous_counter, previous_time = counter, report.telemetry.runtime
            sector_index += 1


def export_log(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError("Cannot overwrite source")
    rows = 0
    with target.open("x", newline="", encoding="utf-8-sig") as output:
        writer = csv.writer(output)
        writer.writerow(["sector", "record_counter", "missing_counter_count", "runtime", "tms_mode", "running", "acquiring", "thrust_enable", "thrust_command", "motor_voltage", "motor_current", "load_cell", "pressure_firmware_units", "battery_voltage", "raw_load_cell", "raw_pressure", "raw_current", "raw_motor_voltage", "raw_battery_voltage", "valid", "calibrated", "sample_counter", "fault", "thruster_age_ms", "thruster_battery_percent", "thruster_payload_hex"])
        for sector, counter, missing, report in iter_records(source):
            s, t = report.status, report.telemetry
            writer.writerow([sector, counter, missing, t.runtime, s.mode.name, int(s.mode_run), int(s.acquire), int(s.thrust_enable), s.thrust_command, t.motor_voltage, t.motor_current, t.load_cell, t.pressure, report.battery_voltage, *report.raw, int(report.valid), report.calibrated, report.counter, report.fault, report.thruster_age_ms, report.thruster.battery_percent, report.thruster_payload.hex()])
            rows += 1
    return rows


def main():
    parser = argparse.ArgumentParser(description="Extract TMS SD sectors to firmware-format CSV (pressure units unconfirmed)")
    parser.add_argument("source")
    parser.add_argument("target")
    args = parser.parse_args()
    print(f"Exported {export_log(args.source, args.target)} records")


if __name__ == "__main__":
    main()
