from pathlib import Path
import time

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from tms_pc.config.settings import Settings
from tms_pc.controller import TMSController
from tms_pc.gui.main_window import MainWindow
from tms_pc.models.enums import Mode, PacketType


def test_five_second_csv_profile_from_gui(app, monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "examples/throttle_30_40_50_40_30_5s.csv"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(path), ""))
    c = TMSController(Settings(mock_period_s=0.02))
    c.recorder.root = tmp_path
    w = MainWindow(c)

    def wait(predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        assert predicate()

    try:
        w.load_profile()
        wait(lambda: c.measurement.profile is not None)
        assert c.measurement.profile.interpolation == "zoh"
        assert path.name in w.profile_info.text()
        assert not w.profile_on.isChecked()
        w.profile_on.setChecked(True)
        assert w.start.text() == "Start CSV Profile"
        c.connect_mock()
        wait(lambda: c.state.connected and c.telemetry is not None)
        for kind, value in [(PacketType.COMMAND_MODE, Mode.MEASUREMENT),
                            (PacketType.COMMAND_THRUST_ENABLE, True)]:
            c.request(kind, value)
            wait(lambda: not c.pending)
        started_at = time.monotonic()
        w.start_measurement()
        wait(lambda: c.state.status.mode_run and not c.pending)
        transitions = []
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            app.processEvents()
            value = c.state.status.thrust_command
            if value and (not transitions or transitions[-1][1] != value):
                transitions.append((c.measurement.position, value))
            if not c.state.status.mode_run and not c.pending and not c.stopping:
                break
            QTest.qWait(10)
        assert [v for _, v in transitions] == [30, 40, 50, 40, 30]
        assert all(abs(t - expected) < 0.3 for (t, _), expected in zip(transitions, [0, 5, 10, 15, 20]))
        assert 24.5 <= time.monotonic() - started_at < 29
        assert not c.state.status.mode_run
        assert not c.state.status.thrust_enable
        assert c.state.status.thrust_command == 0
        assert not c.measurement.use_profile
        # The same loaded file must not prevent a new manual session.
        w.profile_on.setChecked(False)
        assert w.start.text() == "Start"
        for kind, value in [(PacketType.COMMAND_MODE, Mode.STANDBY),
                            (PacketType.COMMAND_MODE, Mode.MEASUREMENT),
                            (PacketType.COMMAND_THRUST_ENABLE, True)]:
            c.request(kind, value)
            wait(lambda: not c.pending)
        w.start_measurement()
        wait(lambda: c.state.status.mode_run and not c.pending)
        w.update_state()
        assert w.send_thrust.isEnabled()
        assert w.send_thrust.text() == "Send Throttle Command"
        w.constant.setValue(30)
        w.send_thrust.click()
        wait(lambda: c.state.status.thrust_command == 30 and not c.pending)
        assert not c.measurement.use_profile
        assert c.telemetry.load_cell > 0
        c.stop()
        wait(lambda: not c.stopping and not c.pending)
        print("Verified GUI CSV transitions:", transitions, "; final throttle=0, Run=False, Enable=False")
    finally:
        w.close()
        c.timer.stop()
        app.processEvents()
