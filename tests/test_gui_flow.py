"""Qt widget-event verification, independent of desktop input automation."""
from pathlib import Path
import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QListWidget, QPushButton
from tms_pc.config.settings import Settings
from tms_pc.controller import TMSController
from tms_pc.gui.main_window import MainWindow
from tms_pc.models.enums import Mode, MeasurementState


def wait_for(app, predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    assert predicate(), "GUI feedback condition timed out"


def test_voltage_display_disconnect_reconnect(app):
    c = TMSController(Settings(mock_period_s=.02))
    window = MainWindow(c)
    window.show()
    try:
        click(app, window, window.connect_button)
        wait_for(app, lambda: c.state.connected and c.telemetry is not None)
        window.refresh_live()
        assert "Voltage 24." in window.sensor_label.text()
        for _ in range(3):
            click(app, window, window.disconnect_button)
            window.refresh_live()
            assert "N/A V" in window.sensor_label.text()
            wait_for(app, lambda: window.connect_button.isEnabled())
            click(app, window, window.connect_button)
            wait_for(app, lambda: c.state.connected and c.telemetry is not None)
            window.refresh_live()
            assert "Voltage 24." in window.sensor_label.text()
            before = c.telemetry.runtime
            wait_for(app, lambda: c.telemetry.runtime > before)
            assert window.live_curves[0][0].getData()[0] is not None
        capture(app, window, "06_reconnected_voltage")
    finally:
        window.close()
        c.timer.stop()
        app.processEvents()


def click(app, window, button):
    assert button.isVisible(), button.text()
    assert button.isEnabled(), button.text()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    wait_for(app, lambda: not window.controller.pending)


def navigate(app, window, row):
    navigation = window.findChild(QListWidget)
    rectangle = navigation.visualItemRect(navigation.item(row))
    QTest.mouseClick(navigation.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
    app.processEvents()
    assert window.pages.currentIndex() == row


def capture(app, window, name):
    directory = Path(__file__).resolve().parents[1] / "artifacts/gui_review"
    directory.mkdir(parents=True, exist_ok=True)
    window.refresh_live()
    app.processEvents()
    assert window.grab().save(str(directory / f"{name}.png"))


def test_calibration_measurement_stop_standby_buttons(app):
    c = TMSController(Settings(mock_period_s=.02))
    window = MainWindow(c)
    window.show()
    try:
        click(app, window, window.connect_button)
        wait_for(app, lambda: c.state.connected and c.telemetry is not None)
        capture(app, window, "01_standby")
        assert not window.enable.isEnabled()
        assert not window.start.isEnabled()
        navigate(app, window, 1)
        click(app, window, window.mode_buttons[Mode.CALIBRATION])
        for reference in (0, 5, 10):
            window.reference.setValue(reference)
            click(app, window, window.acquire_start)
            wait_for(app, lambda: len(c.calibration.samples) >= 5)
            click(app, window, window.acquire_stop)
            click(app, window, window.add_point)
        calculate = next(b for b in window.findChildren(QPushButton) if b.text() == "Calculate Regression")
        click(app, window, calculate)
        assert window.factors.slope == pytest.approx(1000, rel=.002)
        assert window.calibration_table.rowCount() == 3
        assert window.apply_calibration.isEnabled()
        click(app, window, window.apply_calibration)
        capture(app, window, "02_calibration")
        navigate(app, window, 2)
        click(app, window, window.mode_buttons[Mode.MEASUREMENT])
        assert not window.start.isEnabled()
        click(app, window, window.enable)
        assert c.state.measurement == MeasurementState.READY
        click(app, window, window.start)
        assert c.state.measurement == MeasurementState.RUNNING
        window.constant.setValue(50)
        click(app, window, window.send_thrust)
        wait_for(app, lambda: c.telemetry.load_cell > 8)
        assert c.commanded == 50
        assert c.state.status.thrust_command == 50
        capture(app, window, "03_measurement")
        click(app, window, window.stop)
        wait_for(app, lambda: not c.stopping and not c.pending)
        assert c.state.measurement == MeasurementState.FINISHED
        assert c.state.status.thrust_command == 0
        assert not c.state.status.thrust_enable
        assert not window.send_thrust.isEnabled()
        capture(app, window, "04_stopped")
        navigate(app, window, 0)
        click(app, window, window.mode_buttons[Mode.STANDBY])
        assert c.state.status.mode == Mode.STANDBY
        capture(app, window, "05_return_standby")
    finally:
        window.close()
        c.timer.stop()
        app.processEvents()
