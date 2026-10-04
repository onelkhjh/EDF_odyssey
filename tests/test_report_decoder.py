import struct
import pytest
from tms_pc.communication.report_decoder import ReportDecoder


def fixture_payload(prefix):
    # Pack at C field offsets independently of decoder format.
    data = bytearray(72)
    for offset, fmt, values in [
        (0, "I", (0xffffffff,)), (4, "d", (123.456789,)),
        (12, "f", (12.5,)), (16, "4f", (1., 2., 3., 4.)),
        (32, "f", (24.,)), (36, "f", (8.5,)),
        (40, "4f", (11., 12., 13., 14.)), (56, "f", (3.3,)),
        (60, "f", (87.5,)), (64, "B", (0xa5,)), (65, "7s", (bytes(7),)),
    ]:
        struct.pack_into(prefix + fmt, data, offset, *values)
    return bytes(data)


@pytest.mark.parametrize("order,prefix", [("little", "<"), ("big", ">")])
def test_report_field_offsets(order, prefix):
    report = ReportDecoder(byte_order=order).decode(fixture_payload(prefix))
    assert report.packet_counter == 0xffffffff
    assert report.ref_time == pytest.approx(123.456789, abs=1e-9)
    assert report.thrust == 12.5
    assert report.deg == (1., 2., 3., 4.)
    assert report.voltage_edf == 24.
    assert report.current_edf == 8.5
    assert report.deg_m == (11., 12., 13., 14.)
    assert report.logic_voltage == pytest.approx(3.3)
    assert report.battery_percent == 87.5
    assert report.subsystem_status == 0xa5
    assert report.padding == bytes(7)


@pytest.mark.parametrize("size", [0, 64, 71, 73, 136])
def test_report_invalid_length(size):
    with pytest.raises(ValueError, match="exactly 72 bytes"):
        ReportDecoder(byte_order="little").decode(bytes(size))


@pytest.mark.parametrize("offset,fmt", [(4, "d"), (12, "f"), (32, "f"), (56, "f"), (60, "f")])
def test_report_nonfinite(offset, fmt):
    data = bytearray(fixture_payload("<"))
    struct.pack_into("<" + fmt, data, offset, float("nan"))
    with pytest.raises(ValueError, match="non-finite"):
        ReportDecoder(byte_order="little").decode(bytes(data))


def test_report_matches_firmware_padding_and_time_validation():
    data = bytearray(fixture_payload("<"))
    data[71] = 1
    with pytest.raises(ValueError, match="padding"):
        ReportDecoder(byte_order="little").decode(data)
    data[71] = 0
    struct.pack_into("<d", data, 4, -1.)
    with pytest.raises(ValueError, match="negative ref_time"):
        ReportDecoder(byte_order="little").decode(data)


def test_report_requires_explicit_byte_order():
    with pytest.raises(TypeError):
        ReportDecoder()
    with pytest.raises(ValueError):
        ReportDecoder(byte_order="native")
