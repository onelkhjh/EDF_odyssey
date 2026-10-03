from pathlib import Path
import numpy as np
import pytest
from tms_pc.communication.packet import MockCodec, Packet
from tms_pc.communication.mock_transport import MockTransport
from tms_pc.models.enums import Mode, PacketType, MeasurementState
from tms_pc.models.status import Status
from tms_pc.models.calibration import CalibrationPoint
from tms_pc.models.measurement import ThrustProfile
from tms_pc.managers.state_manager import StateManager
from tms_pc.managers.calibration_manager import CalibrationManager
from tms_pc.analysis.statistics import statistics
from tms_pc.analysis.validation import load_csv
from tms_pc.managers.analysis_manager import analyze, export_result
from tms_pc.analysis.electrical import electrical
import pandas as pd


def test_packet_stream_and_corruption():
    codec = MockCodec()
    packet = Packet(PacketType.STATUS, Status(mode=Mode.STANDBY))
    raw = codec.encode(packet)
    assert codec.feed(raw[:4]) == []
    assert codec.feed(raw[4:])[0].value == packet.value
    assert len(codec.feed(raw + raw)) == 2
    bad = bytearray(raw)
    bad[-1] ^= 1
    assert codec.feed(bytes(bad)) == []
    assert codec.errors
    assert codec.feed(raw)[0].kind == PacketType.STATUS
    assert codec.feed(b"TM\xff\x00\x00") == []
    assert codec.errors
    assert codec.feed(b"TM\x01\xff\xff") == []
    assert codec.errors


def test_state_guards_and_observation():
    manager = StateManager()
    manager.connected = True
    manager.observe(Status(mode=Mode.STANDBY))
    with pytest.raises(ValueError):
        manager.guard(PacketType.COMMAND_MODE_RUN, True)
    with pytest.raises(ValueError):
        manager.guard(PacketType.COMMAND_THRUST, 50)
    manager.observe(Status(mode=Mode.MEASUREMENT))
    with pytest.raises(ValueError):
        manager.guard(PacketType.COMMAND_MODE_RUN, True)
    manager.observe(Status(mode=Mode.MEASUREMENT, thrust_enable=True))
    manager.guard(PacketType.COMMAND_MODE_RUN, True)
    assert manager.measurement == MeasurementState.READY
    manager.connected = False
    with pytest.raises(ValueError):
        manager.guard(PacketType.COMMAND_THRUST, 0)


def test_calibration():
    manager = CalibrationManager()
    manager.points = [CalibrationPoint(f, 10, 1000 * f + 100, 0) for f in (0, 0.5, 1, 2)]
    result = manager.fit()
    assert result.slope == pytest.approx(1000)
    assert result.offset == pytest.approx(100)
    assert result.r_squared == pytest.approx(1)


def test_profile(tmp_path):
    profile = ThrustProfile(np.array([0., 1.]), np.array([0., 100.]))
    assert profile.value(0.5) == 50
    bad = tmp_path / "bad.csv"
    bad.write_text("time_s,thrust_percent\n0,0\n0,100\n")
    with pytest.raises(ValueError):
        ThrustProfile.load(bad)


def test_statistics_and_energy():
    result = statistics(np.array([1., 2., 3.]))
    assert result["mean"] == 2
    assert result["std"] == pytest.approx(np.sqrt(2 / 3))
    assert result["rms"] == pytest.approx(np.sqrt(14 / 3))
    frame = pd.DataFrame({"runtime": [0, 0.3, 2], "motor_voltage": [10] * 3, "motor_current": [2] * 3})
    assert electrical(frame)["energy_j"] == 40


def test_analysis_export(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/sample_log.csv"
    data = load_csv(source)
    assert not data.fatal
    result = analyze(data, 0, 6)
    assert result.summary["tracking_rmse_n"] is None
    assert result.summary["energy_j"] > 0
    paths = export_result(result, tmp_path)
    assert len(paths) == 5
    assert all(p.exists() for p in paths)


def test_mock_start_stop_feedback():
    mock = MockTransport()
    codec = MockCodec()
    mock.connect()
    codec.feed(mock.read())
    for kind, value in [(PacketType.COMMAND_MODE, Mode.MEASUREMENT), (PacketType.COMMAND_THRUST_ENABLE, True), (PacketType.COMMAND_MODE_RUN, True), (PacketType.COMMAND_THRUST, 50.)]:
        mock.send(codec.encode(Packet(kind, value)))
        packets = codec.feed(mock.read())
        assert any(p.kind == PacketType.STATUS for p in packets)
    assert mock.state.status.thrust_command == 50
    for kind, value in [(PacketType.COMMAND_THRUST, 0.), (PacketType.COMMAND_THRUST_ENABLE, False), (PacketType.COMMAND_MODE_RUN, False)]:
        mock.send(codec.encode(Packet(kind, value)))
        codec.feed(mock.read())
    assert not mock.state.status.mode_run
    assert not mock.state.status.thrust_enable
    assert mock.state.status.thrust_command == 0
    mock.disconnect()
