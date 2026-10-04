import math
import struct
import time
import pytest
from tms_pc.communication.firmware_codec import FirmwareCodec, decode_report
from tms_pc.communication.firmware_log import iter_records, export_log
from tms_pc.communication.packet import Packet
from tms_pc.controller import TMSController
from tms_pc.models.enums import Mode, PacketType
from PySide6.QtTest import QTest
from tms_pc.managers.communication_manager import CommunicationManager
from tms_pc.config.settings import Settings


def report_payload(mode=4, running=1, enable=1, calibrated=3, fault=0):
    data = bytearray(136)
    struct.pack_into("<4Bf", data, 0, mode, running, 0, enable, 25.0)
    struct.pack_into("<d4f", data, 8, 1.25, 24.0, 3.0, 5.0, 1.0)
    struct.pack_into("<5H2Bf3I", data, 32, 123, 234, 345, 456, 567, 1, calibrated, 12.0, 99, fault, 10)
    struct.pack_into("<fB", data, 120, 87.5, 0xa5)
    return bytes(data)


def wire(payload):
    # Independent firmware byte-sum fixture (no codec encoder).
    body = bytes([65, 66, 0, 0]) + payload
    checksum = 0
    for byte in body:
        checksum += byte
    return body + checksum.to_bytes(4, "little")


def test_command_golden_bytes_and_mode_mapping():
    codec = FirmwareCodec()
    encoded = codec.encode(Packet(PacketType.COMMAND_THRUST, 50))
    assert encoded == b"AB\0\0" + b"\x05" + bytes(7) + b"\0\0\x48\x42" + bytes(20) + b"\x12\x01\0\0"
    for mode, number in ((Mode.SAFE, 0), (Mode.STANDBY, 2), (Mode.CALIBRATION, 3), (Mode.MEASUREMENT, 4)):
        assert codec.encode(Packet(PacketType.COMMAND_MODE, mode))[5] == number
    assert codec.encode(Packet(PacketType.STOP, None))[4] == 8
    assert codec.encode(Packet(PacketType.HEARTBEAT, None))[4] == 7
    assert struct.unpack_from("<dd", codec.encode(Packet(PacketType.COMMAND_CALIBRATION_FACTOR, (1000., 100.))), 20) == (1000., 100.)


def test_fragmentation_checksum_and_stream_recovery():
    good = wire(report_payload())
    bad = bytearray(good)
    bad[20] ^= 1
    codec = FirmwareCodec()
    assert codec.feed(b"garbage" + bad + good[:55]) == []
    assert codec.errors
    packets = codec.feed(good[55:] + good)
    assert len(packets) == 2
    report = packets[0].value
    assert report.status.mode == Mode.MEASUREMENT
    assert report.telemetry.runtime == 1.25
    assert report.raw == (123, 234, 345, 456, 567)
    assert report.counter == 99
    assert len(report.thruster_payload) == 72
    assert report.thruster.battery_percent == 87.5
    assert report.thruster.subsystem_status == 0xa5


def test_unqualified_sensor_values_are_not_presented_as_measurements():
    report = decode_report(report_payload(calibrated=0))
    assert math.isnan(report.telemetry.load_cell)
    assert math.isnan(report.telemetry.motor_voltage)
    assert report.telemetry.raw_load_cell == 123
    data = bytearray(report_payload())
    struct.pack_into("<f", data, 24, math.nan)
    assert math.isnan(decode_report(data).telemetry.load_cell)
    assert "SD" in decode_report(report_payload(fault=4)).fault_text


def test_sd_records_gaps_tail_and_corruption(tmp_path):
    def sector(counter):
        return wire(struct.pack("<II", counter, 0) + report_payload()) + bytes(360)
    source = tmp_path / "DATA0000.BIN"
    source.write_bytes(sector(10) + sector(13) + bytes(1024))
    records = list(iter_records(source))
    assert len(records) == 2 and records[1][2] == 2
    output = tmp_path / "out.csv"
    assert export_log(source, output) == 2
    assert "pressure_firmware_units" in output.read_text(encoding="utf-8-sig")
    import csv
    with output.open(encoding="utf-8-sig") as file:
        assert next(csv.DictReader(file))["thruster_battery_percent"] == "87.5"
    with pytest.raises(FileExistsError):
        export_log(source, output)
    source.write_bytes(sector(10) + bytes([1]) + sector(13)[1:])
    with pytest.raises(ValueError, match="sector 1"):
        list(iter_records(source))


def hardware_controller():
    c = TMSController()
    c.timer.stop()
    c.hardware = True
    c.accept_packets = True
    c._packet(Packet(PacketType.HARDWARE_REPORT, decode_report(report_payload())))
    return c


def test_fault_blocks_thrust_and_stop_uses_firmware_atomic_command(app):
    c = hardware_controller()
    c._packet(Packet(PacketType.HARDWARE_REPORT, decode_report(report_payload(fault=4))))
    with pytest.raises(ValueError, match="fault"):
        c.request(PacketType.COMMAND_THRUST, 10.)
    c.stop()
    outgoing = c.communication.queue.get_nowait()[2]
    assert outgoing.packet.kind == PacketType.STOP
    token = outgoing.token
    c._sent(token, time.monotonic())
    data = bytearray(report_payload(mode=2, running=0, enable=0))
    struct.pack_into("<f", data, 4, 0.)
    c._packet(Packet(PacketType.HARDWARE_REPORT, decode_report(data)))
    assert not c.pending and not c.stopping


def test_calibration_requires_run_and_never_fabricates_factor_feedback(app):
    c = hardware_controller()
    c._packet(Packet(PacketType.HARDWARE_REPORT, decode_report(report_payload(mode=3, running=0, enable=0))))
    with pytest.raises(ValueError, match="coefficient"):
        c.request(PacketType.COMMAND_CALIBRATION_FACTOR, (1000., 100.))
    c.request(PacketType.COMMAND_CALIBRATION_ACQUIRE, True)
    outgoing = c.communication.queue.get_nowait()[2]
    assert outgoing.packet == Packet(PacketType.COMMAND_MODE_RUN, True)
    c._sent(outgoing.token, time.monotonic())
    c._packet(Packet(PacketType.HARDWARE_REPORT, decode_report(report_payload(mode=3, running=1, enable=0))))
    assert c.communication.queue.get_nowait()[2].packet == Packet(PacketType.COMMAND_CALIBRATION_ACQUIRE, True)


def test_worker_sends_real_heartbeat_and_delivers_report(app):
    class Transport:
        def __init__(self):
            self.sent = []
            self.closed = False
        def connect(self):
            pass
        def send(self, data):
            self.sent.append((time.monotonic(), data))
        def read(self):
            return wire(report_payload())
        def disconnect(self):
            self.closed = True
    transport = Transport()
    manager = CommunicationManager(Settings(hardware_heartbeat_s=.05))
    received = []
    manager.packet_received.connect(lambda session, packet: received.append(packet))
    manager.connect_transport(transport, FirmwareCodec())
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and (len(transport.sent) < 3 or not received):
            app.processEvents()
            QTest.qWait(10)
        assert len(transport.sent) >= 3
        assert all(len(data) == 40 and data[4] == 7 for _, data in transport.sent)
        assert all(b[0] - a[0] < .5 for a, b in zip(transport.sent, transport.sent[1:]))
        assert received[0].kind == PacketType.HARDWARE_REPORT
    finally:
        manager.disconnect()
        manager.thread.join(1)
        app.processEvents()
    assert transport.closed and not manager.thread.is_alive()


def test_stale_status_sends_safe_then_requires_reconnect(app):
    c = hardware_controller()
    c.last_status_at = time.monotonic() - 1
    c._tick()
    assert c.hardware_status_lost and c.stopping
    outgoing = c.communication.queue.get_nowait()[2]
    assert outgoing.packet == Packet(PacketType.COMMAND_MODE, Mode.SAFE)
    for expected in c.pending.values():
        expected.queued_at -= 2
    c._tick()
    c._tick()
    assert not c.state.connected and not c.accept_packets
    assert "RECONNECT" in c.message


def test_old_report_and_corrupt_new_thruster_are_rejected():
    with pytest.raises(ValueError, match="136 bytes"):
        decode_report(bytes(128))
    codec = FirmwareCodec()
    data = bytearray(report_payload())
    data[131] = 1
    assert codec.feed(wire(data) + wire(report_payload()))[0].value.thruster.battery_percent == 87.5
    assert codec.errors == ["report_t padding must be zero"]
