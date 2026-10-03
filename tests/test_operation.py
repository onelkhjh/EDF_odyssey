from pathlib import Path
from dataclasses import replace
import time
import pytest
from PySide6.QtTest import QTest
from tms_pc.controller import TMSController
from tms_pc.config.settings import Settings
from tms_pc.gui.main_window import MainWindow
from tms_pc.models.enums import Mode, PacketType, MeasurementState
from tms_pc.models.measurement import ThrustProfile
from tms_pc.models.status import Status
from tms_pc.communication.packet import Packet
from tms_pc.analysis.validation import load_csv
from tms_pc.managers.analysis_manager import analyze


def until(app, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(5)
    assert predicate(), "Timed out waiting for asynchronous feedback"


@pytest.fixture
def controller(app):
    c = TMSController(Settings(mock_period_s=0.01, connection_timeout_s=0.3,
                               mock_watchdog_s=0.4, mock_command_refresh_s=0.1))
    c.connect_mock()
    until(app, lambda: c.state.connected and c.telemetry is not None)
    yield c
    c.timer.stop()
    c.disconnect()
    c.communication.thread.join(timeout=1)
    app.processEvents()


def command(app, c, kind, value):
    c.request(kind, value)
    until(app, lambda: not c.pending)


def start(app, c):
    command(app, c, PacketType.COMMAND_MODE, Mode.MEASUREMENT)
    command(app, c, PacketType.COMMAND_THRUST_ENABLE, True)
    command(app, c, PacketType.COMMAND_MODE_RUN, True)
    assert c.state.measurement == MeasurementState.RUNNING


def test_full_measurement_and_watchdog_refresh(app, controller):
    c = controller
    start(app, c)
    command(app, c, PacketType.COMMAND_THRUST, 50)
    until(app, lambda: c.telemetry.load_cell > 5)
    QTest.qWait(600)
    app.processEvents()
    assert c.state.status.mode_run
    assert c.state.status.thrust_command == 50
    c.stop()
    until(app, lambda: not c.stopping and not c.pending)
    assert c.state.status.thrust_command == 0
    assert not c.state.status.thrust_enable
    assert not c.state.status.mode_run
    assert c.state.measurement == MeasurementState.FINISHED
    command(app, c, PacketType.COMMAND_MODE, Mode.STANDBY)
    assert c.state.status.mode == Mode.STANDBY


def test_loss_inhibits_commands(app, controller):
    c = controller
    start(app, c)
    c.transport.lost.set()
    until(app, lambda: not c.state.connected)
    assert "LOST" in c.message
    with pytest.raises(ValueError):
        c.request(PacketType.COMMAND_THRUST, 30)
    assert not c.pending


def test_profile_runtime_completion(app, controller, tmp_path):
    c = controller
    path = tmp_path / "profile.csv"
    path.write_text("time_s,thrust_percent\n0,0\n0.15,60\n0.3,0\n")
    c.measurement.profile = ThrustProfile.load(path)
    c.measurement.use_profile = True
    start(app, c)
    until(app, lambda: not c.state.status.mode_run and not c.pending and not c.stopping)
    assert c.state.status.thrust_command == 0
    assert not c.state.status.thrust_enable


def test_gui_analysis_and_render(app, controller, tmp_path):
    window = MainWindow(controller)
    try:
        window.show()
        app.processEvents()
        window.refresh_live()
        assert "Runtime" in window.sensor_label.text()
        assert "white" in window.styleSheet()
        path = Path(__file__).resolve().parents[1] / "examples/sample_log.csv"
        window.analysis_done([load_csv(path)])
        until(app, lambda: bool(window.results))
        assert "energy_j" in window.analysis_text.toPlainText()
        window.pages.setCurrentIndex(3)
        window.plot_analysis()
        app.processEvents()
        assert window.grab().save(str(tmp_path / "gui.png"))
        import pyqtgraph.exporters
        exporter = pyqtgraph.exporters.ImageExporter(window.analysis_plot.plotItem)
        exporter.export(str(tmp_path / "graph.png"))
        assert (tmp_path / "graph.png").stat().st_size > 0
    finally:
        window.close()


def test_async_calibration(app, controller):
    c = controller
    command(app, c, PacketType.COMMAND_MODE, Mode.CALIBRATION)
    for reference in (0., 1., 2.):
        c.calibration.reference_n = reference
        c.transport.reference_n = reference
        command(app, c, PacketType.COMMAND_CALIBRATION_ACQUIRE, True)
        until(app, lambda: len(c.calibration.samples) >= 5)
        command(app, c, PacketType.COMMAND_CALIBRATION_ACQUIRE, False)
        c.calibration.add_point()
    fit = c.calibration.fit()
    assert fit.slope == pytest.approx(1000, rel=0.002)
    command(app, c, PacketType.COMMAND_CALIBRATION_FACTOR, (fit.slope, fit.offset))
    assert c.state.status.slope == pytest.approx(fit.slope)


def test_missing_feedback_stop_is_bounded(app, controller):
    c = controller
    start(app, c)
    c.settings = replace(c.settings, feedback_timeout_s=0.04)
    warnings = []
    c.warning.connect(warnings.append)
    original_send = c.transport.send

    def ignore_thrust(data):
        decoded = c.transport.codec.feed(data)
        for packet in decoded:
            if packet.kind != PacketType.COMMAND_THRUST:
                original_send(c.transport.codec.encode(packet))

    c.transport.send = ignore_thrust
    c.request(PacketType.COMMAND_THRUST, 50.)
    until(app, lambda: c.state.status.mode == Mode.SAFE and not c.pending and not c.stopping)
    assert any("FEEDBACK TIMEOUT" in message for message in warnings)
    assert not c.state.status.mode_run
    assert not c.state.status.thrust_enable


def test_disconnect_ignores_late_packets(app, controller):
    c = controller
    c.disconnect()
    c._packet(Packet(PacketType.STATUS, Status(mode=Mode.MEASUREMENT, mode_run=True, thrust_enable=True)))
    assert not c.state.connected
    with pytest.raises(ValueError):
        c.request(PacketType.COMMAND_THRUST, 10)


def test_calibration_sample_limit(app, controller):
    c = controller
    c.settings = replace(c.settings, calibration_max_samples=3)
    command(app, c, PacketType.COMMAND_MODE, Mode.CALIBRATION)
    command(app, c, PacketType.COMMAND_CALIBRATION_ACQUIRE, True)
    until(app, lambda: not c.state.status.acquire and not c.pending)
    assert len(c.calibration.samples) == 3


def test_reconnect_ignores_previous_session_events(app, controller):
    c = controller
    old_session = c.communication.session
    c.disconnect()
    c.communication.thread.join(timeout=1)
    # Do not drain old queued Qt disconnect signals before opening a new session.
    c.connect_mock()
    until(app, lambda: c.state.connected and c.telemetry is not None)
    assert c.communication.session > old_session
    c._session_connection(old_session, False, "DISCONNECTED")
    c._session_packet(old_session, Packet(PacketType.STATUS, Status(mode=Mode.MEASUREMENT, mode_run=True, thrust_enable=True)))
    assert c.state.connected
    assert c.state.status.mode == Mode.STANDBY
    before = c.telemetry.runtime
    until(app, lambda: c.telemetry.runtime > before)
    assert 23 < c.telemetry.motor_voltage < 25


def test_immediate_reconnect_is_nonblocking(app, controller):
    c = controller
    for _ in range(3):
        c.disconnect()
        assert c.telemetry is None
        c.connect_mock()
        until(app, lambda: c.state.connected and c.telemetry is not None and not c.reconnect_requested)
        assert 23 < c.telemetry.motor_voltage < 25
