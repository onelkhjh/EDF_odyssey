from pathlib import Path
import logging
import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel, QComboBox, QLineEdit, QDoubleSpinBox, QStackedWidget, QListWidget, QFileDialog, QTableWidget, QTableWidgetItem, QCheckBox, QPlainTextEdit, QSplitter)
from tms_pc.controller import TMSController
from tms_pc.config.settings import BAUD_RATE_OPTIONS
from tms_pc.communication.serial_transport import available_ports
from tms_pc.models.enums import Mode, PacketType, MeasurementState
from tms_pc.models.measurement import ThrustProfile
from tms_pc.managers.analysis_manager import AnalysisManager, AnalysisResult, analyze, export_result

CHANNELS = {"Voltage (V)": "motor_voltage", "Current (A)": "motor_current", "Thrust (N)": "load_cell", "Pressure (kPa)": "pressure", "Command (%)": "thrust_command", "Power (W)": "power_w"}
COLORS = ["#2563eb", "#059669", "#dc2626", "#9333ea", "#d97706", "#0891b2"]


def spin(minimum: float, maximum: float, value: float = 0, suffix: str = "") -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(3)
    widget.setValue(value)
    widget.setSuffix(suffix)
    return widget


class MainWindow(QMainWindow):
    def __init__(self, controller: TMSController, mock: bool = False) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("TMS-PC · EDF Thrust Measurement System")
        self.resize(1320, 900)
        pg.setConfigOptions(background="w", foreground="#334155", antialias=True)
        self.setStyleSheet("QWidget { background: white; color: #172033; font-size: 13px; } QPushButton { background: #eef4ff; border: 1px solid #cbd5e1; padding: 8px; border-radius: 4px; } QPushButton:disabled { color: #94a3b8; background: #f8fafc; } QLineEdit,QDoubleSpinBox,QComboBox { border: 1px solid #cbd5e1; padding: 5px; } QListWidget::item { padding: 16px; } QListWidget::item:selected { background: #dbeafe; color: #1d4ed8; }")
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("TMS-PC  /  EDF Ground Control")
        title.setStyleSheet("font-size: 24px; font-weight: 600; padding: 8px;")
        layout.addWidget(title)
        bar = QHBoxLayout()
        self.ports = QComboBox()
        self.ports.addItem("Mock TMS")
        self.baud = QComboBox()
        self.baud.setEditable(True)
        self.baud.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.baud.addItems(["", *(str(rate) for rate in BAUD_RATE_OPTIONS)])
        self.baud.lineEdit().setPlaceholderText("Select / enter baud (TBD)")
        self.baud.setToolTip("Serial baud rate in bit/s. Select a value matching the firmware or enter a custom integer. Mock does not use baud rate.")
        if controller.settings.hardware_baud is not None:
            self.baud.setCurrentText(str(controller.settings.hardware_baud))
        self.baud.setMaximumWidth(180)
        bar.addWidget(self.ports)
        bar.addWidget(QLabel("Baud (bit/s)"))
        bar.addWidget(self.baud)
        self.button(bar, "Refresh COM", self.refresh_ports)
        self.connect_button = self.button(bar, "Connect", self.connect_device)
        self.disconnect_button = self.button(bar, "Disconnect", controller.disconnect)
        self.link = QLabel("DISCONNECTED")
        bar.addWidget(self.link, 1)
        layout.addLayout(bar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        split = QSplitter()
        navigation = QListWidget()
        navigation.addItems(["Standby", "Calibration", "Measurement", "Analysis"])
        navigation.setMaximumWidth(180)
        self.pages = QStackedWidget()
        split.addWidget(navigation)
        split.addWidget(self.pages)
        layout.addWidget(split, 1)
        navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.mode_buttons: dict[Mode, QPushButton] = {}
        self.live_curves: list[tuple[object, str]] = []
        self.standby_page()
        self.calibration_page()
        self.measurement_page()
        self.analysis_page()
        navigation.setCurrentRow(0)
        self.message = QLabel("DISCONNECTED")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        safety = QLabel("PC는 안전 시스템이 아닙니다. 최종 추진기 정지와 통신 Timeout 안전 동작은 TMS Firmware가 수행합니다.")
        safety.setStyleSheet("color: #9a3412; background: #fff7ed; padding: 8px;")
        layout.addWidget(safety)
        controller.changed.connect(self.update_state)
        controller.warning.connect(self.show_error)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_live)
        self.timer.start(controller.settings.gui_period_ms)
        self.refresh_ports()
        self.update_state()
        if mock:
            QTimer.singleShot(0, self.connect_device)

    def guard_call(self, function) -> None:
        try:
            function()
        except Exception as exc:
            logging.getLogger(__name__).exception("User action failed")
            self.show_error(str(exc))

    def show_error(self, message: str) -> None:
        self.message.setText(message)
        self.message.setStyleSheet("color: #b91c1c; padding: 6px;")

    def button(self, layout, text: str, function, danger: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(lambda _=False: self.guard_call(function))
        if danger:
            button.setStyleSheet("QPushButton { background: #fee2e2; color: #991b1b; border: 1px solid #ef4444; padding: 8px; }")
        layout.addWidget(button)
        return button

    def page(self, title: str, mode: Mode | None = None) -> QVBoxLayout:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        row = QHBoxLayout()
        label = QLabel(title)
        label.setStyleSheet("font-size: 20px; font-weight: 600;")
        row.addWidget(label, 1)
        if mode:
            self.mode_buttons[mode] = self.button(row, "Enter " + mode.name, lambda: self.controller.request(PacketType.COMMAND_MODE, mode))
        layout.addLayout(row)
        self.pages.addWidget(widget)
        return layout

    def live_plot(self, layout) -> None:
        grid = QGridLayout()
        for index, (label, channel) in enumerate(list(CHANNELS.items())[:5]):
            plot = pg.PlotWidget(title=label)
            plot.setLabel("bottom", "TMS runtime", units="s")
            plot.showGrid(x=True, y=True, alpha=0.2)
            curve = plot.plot(pen=pg.mkPen(COLORS[index], width=2), clipToView=True, autoDownsample=True, downsampleMethod="peak")
            self.live_curves.append((curve, channel))
            grid.addWidget(plot, index // 2, index % 2)
        layout.addLayout(grid, 1)

    def standby_page(self) -> None:
        layout = self.page("Standby · Sensor Monitor", Mode.STANDBY)
        self.sensor_label = QLabel("Waiting for telemetry")
        self.sensor_label.setWordWrap(True)
        layout.addWidget(self.sensor_label)
        row = QHBoxLayout()
        for label in ("Thrust Enable", "Thrust Command", "Measurement Start"):
            button = QPushButton(label)
            button.setEnabled(False)
            row.addWidget(button)
        layout.addLayout(row)
        self.live_plot(layout)

    def calibration_page(self) -> None:
        layout = self.page("Load Cell Calibration", Mode.CALIBRATION)
        row = QHBoxLayout()
        row.addWidget(QLabel("Reference Load"))
        self.reference = spin(-1e6, 1e6, suffix=" N")
        row.addWidget(self.reference)
        self.acquire_start = self.button(row, "Acquire Start", self.start_acquire)
        self.acquire_stop = self.button(row, "Acquire Stop", lambda: self.controller.request(PacketType.COMMAND_CALIBRATION_ACQUIRE, False))
        self.add_point = self.button(row, "Add Point", self.add_calibration_point)
        layout.addLayout(row)
        layout.addWidget(QLabel("Mock acquisition uses this reference as a simulated applied load. Actual TMS must stream RAW values."))
        self.sample_count = QLabel("Samples: 0")
        layout.addWidget(self.sample_count)
        self.calibration_table = QTableWidget(0, 4)
        self.calibration_table.setHorizontalHeaderLabels(["Reference N", "Samples", "Raw Mean", "Raw STD"])
        layout.addWidget(self.calibration_table)
        row = QHBoxLayout()
        self.button(row, "Calculate Regression", self.calculate_calibration)
        self.apply_calibration = self.button(row, "Apply to TMS", self.apply_factors)
        self.button(row, "Clear Points", self.clear_calibration)
        layout.addLayout(row)
        self.calibration_result = QLabel("a / b / Scale Factor / R²: N/A")
        layout.addWidget(self.calibration_result)
        self.cal_plot = pg.PlotWidget(title="Raw = a × Reference Force + b")
        self.cal_plot.setLabel("bottom", "Reference", units="N")
        self.cal_plot.setLabel("left", "Raw counts")
        layout.addWidget(self.cal_plot, 1)
        self.factors = None

    def start_acquire(self) -> None:
        self.controller.request(PacketType.COMMAND_CALIBRATION_ACQUIRE, True)
        self.controller.calibration.samples.clear()
        self.controller.calibration.reference_n = self.reference.value()
        if self.controller.transport:
            self.controller.transport.reference_n = self.reference.value()

    def add_calibration_point(self) -> None:
        if self.controller.state.status.acquire or self.controller.pending:
            raise ValueError("Stop acquisition and wait for feedback first")
        p = self.controller.calibration.add_point()
        row = self.calibration_table.rowCount()
        self.calibration_table.insertRow(row)
        for column, value in enumerate((p.reference_n, p.samples, p.raw_mean, p.raw_std)):
            self.calibration_table.setItem(row, column, QTableWidgetItem(f"{value:.6g}"))
        self.factors = None

    def calculate_calibration(self) -> None:
        self.factors = self.controller.calibration.fit()
        r = self.factors
        self.calibration_result.setText(f"Slope a={r.slope:.6g} raw/N   Zero Offset b={r.offset:.6g} raw   Scale Factor={r.scale_factor:.6g} N/raw   R²={r.r_squared:.8f}")
        points = self.controller.calibration.points
        x = np.array([p.reference_n for p in points])
        y = np.array([p.raw_mean for p in points])
        self.cal_plot.clear()
        self.cal_plot.plot(x, y, pen=None, symbol="o", symbolBrush="#2563eb")
        xx = np.array([x.min(), x.max()])
        self.cal_plot.plot(xx, xx * r.slope + r.offset, pen="#dc2626")
        self.update_state()

    def apply_factors(self) -> None:
        if self.factors is None:
            raise ValueError("Calculate regression first")
        self.controller.request(PacketType.COMMAND_CALIBRATION_FACTOR, (self.factors.slope, self.factors.offset))

    def clear_calibration(self) -> None:
        if self.controller.state.status.acquire:
            raise ValueError("Stop acquisition first")
        self.controller.calibration.points.clear()
        self.controller.calibration.samples.clear()
        self.calibration_table.setRowCount(0)
        self.factors = None
        self.cal_plot.clear()
        self.update_state()

    def measurement_page(self) -> None:
        layout = self.page("Measurement · Separate Enable / Start", Mode.MEASUREMENT)
        self.measurement_label = QLabel()
        layout.addWidget(self.measurement_label)
        row = QHBoxLayout()
        self.enable = self.button(row, "Enable Thrust", lambda: self.controller.request(PacketType.COMMAND_THRUST_ENABLE, True))
        self.disable = self.button(row, "Disable Thrust", self.controller.stop, True)
        self.start = self.button(row, "Start", self.start_measurement)
        self.stop = self.button(row, "Stop", self.controller.stop, True)
        self.emergency = self.button(row, "Emergency Stop Request", lambda: self.controller.stop(True), True)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.constant = spin(0, 100, suffix=" %")
        row.addWidget(QLabel("Constant Thrust"))
        row.addWidget(self.constant)
        self.send_thrust = self.button(row, "Send Thrust Command", lambda: self.controller.request(PacketType.COMMAND_THRUST, self.constant.value()))
        self.profile_on = QCheckBox("Use CSV Profile")
        row.addWidget(self.profile_on)
        self.load_profile_button = self.button(row, "Load Profile CSV", self.load_profile)
        layout.addLayout(row)
        self.profile_info = QLabel("Profile not loaded")
        layout.addWidget(self.profile_info)
        self.profile_plot = pg.PlotWidget(title="Profile Preview · Command % vs Relative TMS Runtime")
        self.profile_plot.setLabel("bottom", "Relative runtime", units="s")
        self.profile_plot.setLabel("left", "Thrust command", units="%")
        self.profile_marker = pg.InfiniteLine(pos=0, pen="#dc2626")
        self.profile_plot.addItem(self.profile_marker)
        layout.addWidget(self.profile_plot, 1)
        self.measure_sensor = QLabel()
        self.measure_sensor.setWordWrap(True)
        layout.addWidget(self.measure_sensor)
        self.live_plot(layout)
        loss_row = QHBoxLayout()
        self.loss_button = self.button(loss_row, "Mock: Force Communication Lost", self.force_loss, True)
        layout.addLayout(loss_row)

    def start_measurement(self) -> None:
        if self.profile_on.isChecked() and self.controller.measurement.profile is None:
            raise ValueError("Load a validated profile first")
        self.controller.measurement.use_profile = self.profile_on.isChecked()
        self.controller.request(PacketType.COMMAND_MODE_RUN, True)

    def load_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Profile CSV", "examples", "CSV (*.csv)")
        if not path:
            return
        # CSV parsing/validation also runs in analysis worker.
        self.analysis_manager.submit(lambda: ("profile", path, ThrustProfile.load(path)))

    def force_loss(self) -> None:
        if self.controller.transport:
            self.controller.transport.lost.set()

    def analysis_page(self) -> None:
        layout = self.page("SD Card CSV · Analysis and Comparison")
        self.analysis_manager = AnalysisManager()
        self.analysis_manager.completed.connect(self.analysis_done)
        self.analysis_manager.failed.connect(self.analysis_failed)
        self.datasets = []
        self.results: list[AnalysisResult] = []
        self.analysis_busy = False
        row = QHBoxLayout()
        self.load_csv_button = self.button(row, "Load CSV Files", self.load_analysis)
        self.align = QCheckBox("Align Start Time")
        self.align.setChecked(True)
        self.align.toggled.connect(self.plot_analysis)
        row.addWidget(self.align)
        self.analysis_channel = QComboBox()
        self.analysis_channel.addItems(CHANNELS)
        self.analysis_channel.addItems(["Thrust vs Power", "Thrust vs Current", "Thrust vs Command", "Power vs Command"])
        self.analysis_channel.currentTextChanged.connect(self.plot_analysis)
        row.addWidget(self.analysis_channel)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.range_start = spin(0, 1e9)
        self.range_end = spin(0, 1e9, 1e9)
        self.manual_step = QCheckBox("Manual Step Time")
        self.step_time = spin(0, 1e9)
        row.addWidget(QLabel("Start Time (s)"))
        row.addWidget(self.range_start)
        row.addWidget(QLabel("End Time (s)"))
        row.addWidget(self.range_end)
        row.addWidget(self.manual_step)
        row.addWidget(self.step_time)
        self.analyze_button = self.button(row, "Analyze Range", self.analyze_range)
        layout.addLayout(row)
        layout.addWidget(QLabel("Range uses original TMS runtime. Alignment affects comparison plots only. Canonical load_cell=N; command=%."))
        self.analysis_plot = pg.PlotWidget(title="Test Comparison")
        self.analysis_plot.addLegend()
        self.analysis_plot.showGrid(x=True, y=True, alpha=0.2)
        layout.addWidget(self.analysis_plot, 2)
        self.analysis_text = QPlainTextEdit()
        self.analysis_text.setReadOnly(True)
        layout.addWidget(self.analysis_text, 1)
        self.validation_table = QTableWidget(0, 5)
        self.validation_table.setHorizontalHeaderLabels(["File", "Severity", "CSV Row", "Column", "Problem"])
        layout.addWidget(self.validation_table, 1)
        row = QHBoxLayout()
        self.export_csv_button = self.button(row, "Export All Results CSV", self.export_csv)
        self.export_png_button = self.button(row, "Export Graph PNG", self.export_png)
        layout.addLayout(row)

    def set_analysis_busy(self, busy: bool) -> None:
        self.analysis_busy = busy
        self.load_csv_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy)
        self.export_csv_button.setEnabled(not busy and bool(self.results))
        if busy:
            self.analysis_text.setPlainText("Working in background…")

    def load_analysis(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Canonical TMS CSV", "examples", "CSV (*.csv)")
        if paths:
            self.set_analysis_busy(True)
            self.analysis_manager.load(paths)

    def analysis_failed(self, message: str) -> None:
        self.set_analysis_busy(False)
        self.show_error(message)
        self.analysis_text.setPlainText(message)

    def analysis_done(self, result) -> None:
        if isinstance(result, tuple) and result[0] == "profile":
            _, path, profile = result
            if self.controller.state.status.mode_run:
                self.show_error("Profile arrived while running; Stop before replacing profile")
                return
            self.controller.measurement.profile = profile
            self.profile_plot.clear()
            self.profile_plot.plot(profile.times, profile.commands, pen=pg.mkPen("#2563eb", width=2))
            self.profile_plot.addItem(self.profile_marker)
            self.profile_info.setText(f"{Path(path).name}: {len(profile.times)} points, duration {profile.times[-1]:.3f} s")
            return
        self.set_analysis_busy(False)
        if isinstance(result, tuple) and result[0] == "export":
            self.analysis_text.appendPlainText("Exported:\n" + "\n".join(str(p) for p in result[1]))
            return
        if result and hasattr(result[0], "issues"):
            self.datasets = result
            self.results = []
            self.validation_table.setRowCount(0)
            for data in result:
                for issue in data.issues:
                    row = self.validation_table.rowCount()
                    self.validation_table.insertRow(row)
                    for col, value in enumerate((data.source.name, issue.severity, issue.row, issue.column, issue.description)):
                        self.validation_table.setItem(row, col, QTableWidgetItem(str(value if value is not None else "—")))
            good = [d for d in result if not d.fatal]
            if not good:
                self.analysis_failed("Fatal validation errors; review the validation table")
                return
            self.range_start.setValue(min(d.frame.runtime.iloc[0] for d in good))
            self.range_end.setValue(max(d.frame.runtime.iloc[-1] for d in good))
            self.analyze_range()
            return
        self.results = result
        text = []
        for r in self.results:
            text.append(r.dataset.source.name + f" · {len(r.selected)} samples")
            text.append(r.statistics.to_string(index=False))
            for key, value in {**r.summary, **r.dynamic}.items():
                text.append(f"{key}: {'N/A' if value is None else value}")
            text.append("Tracking % vs N: N/A. Optional thrust_reference_n enables same-unit error metrics.\n")
        self.analysis_text.setPlainText("\n".join(text))
        self.set_analysis_busy(False)
        self.plot_analysis()

    def analyze_range(self) -> None:
        good = [d for d in self.datasets if not d.fatal]
        if not good:
            raise ValueError("Load valid CSV data first")
        start, end = self.range_start.value(), self.range_end.value()
        step = self.step_time.value() if self.manual_step.isChecked() else None
        self.set_analysis_busy(True)
        self.analysis_manager.submit(lambda: [analyze(data, start, end, step) for data in good])

    def plot_analysis(self, *_args) -> None:
        self.analysis_plot.clear()
        label = self.analysis_channel.currentText()
        scatters = {"Thrust vs Power": ("power_w", "load_cell"), "Thrust vs Current": ("motor_current", "load_cell"), "Thrust vs Command": ("thrust_command", "load_cell"), "Power vs Command": ("thrust_command", "power_w")}
        for index, result in enumerate(self.results):
            frame = result.selected
            color = COLORS[index % len(COLORS)]
            if label in scatters:
                xcol, ycol = scatters[label]
                self.analysis_plot.plot(frame[xcol].to_numpy(), frame[ycol].to_numpy(), pen=None, symbol="o", symbolSize=4, symbolBrush=color, name=result.dataset.source.name)
                self.analysis_plot.setLabel("bottom", xcol)
                self.analysis_plot.setLabel("left", ycol)
            else:
                time = frame.runtime.to_numpy()
                if self.align.isChecked():
                    time = time - result.processed.runtime.iloc[0]
                # Attach the empty curve before enabling clipping; Qt may notify
                # parent changes while a newly populated curve has no ViewBox yet.
                curve = self.analysis_plot.plot(pen=pg.mkPen(color, width=2), name=result.dataset.source.name)
                curve.setClipToView(True)
                curve.setDownsampling(auto=True, method="peak")
                curve.setData(time, frame[CHANNELS[label]].to_numpy())
                self.analysis_plot.setLabel("bottom", "Runtime", units="s")
                self.analysis_plot.setLabel("left", label)

    def export_csv(self) -> None:
        if not self.results:
            raise ValueError("Analyze data first")
        directory = QFileDialog.getExistingDirectory(self, "Export results directory")
        if directory:
            results = list(self.results)
            self.set_analysis_busy(True)
            self.analysis_manager.submit(lambda: ("export", [p for r in results for p in export_result(r, directory)]))

    def export_png(self) -> None:
        if not self.results:
            raise ValueError("Analyze data first")
        path, _ = QFileDialog.getSaveFileName(self, "Export plot PNG", "comparison.png", "PNG (*.png)")
        if path:
            exporter = pg.exporters.ImageExporter(self.analysis_plot.plotItem)
            exporter.parameters()["width"] = 1600
            exporter.export(path)
            self.message.setText("Graph exported: " + path)

    def refresh_ports(self) -> None:
        current = self.ports.currentText()
        self.ports.clear()
        self.ports.addItems(["Mock TMS", *available_ports()])
        if self.ports.findText(current) >= 0:
            self.ports.setCurrentText(current)

    def connect_device(self) -> None:
        if self.ports.currentText() == "Mock TMS":
            self.controller.connect_mock()
        else:
            try:
                baud = int(self.baud.currentText().strip())
                if baud <= 0:
                    raise ValueError()
            except ValueError:
                raise ValueError("Enter a confirmed positive hardware baud rate") from None
            self.controller.connect_serial(self.ports.currentText(), baud)

    def update_state(self) -> None:
        c, s = self.controller, self.controller.state.status
        linked = c.state.connected
        ready = linked and not c.pending and not c.stopping
        worker_active = bool(c.communication.thread and c.communication.thread.is_alive())
        self.baud.setEnabled(not worker_active and not c.reconnect_requested)
        self.ports.setEnabled(not worker_active and not c.reconnect_requested)
        self.connect_button.setEnabled(not linked and not c.reconnect_requested and (not worker_active or c.communication.stop_event.is_set()))
        self.disconnect_button.setEnabled(linked or worker_active or c.reconnect_requested)
        self.link.setText("CONNECTED" if linked else "DISCONNECTED / LOST")
        self.status.setText(f"TMS Mode: {s.mode.name} | Mode Run: {s.mode_run} | Thrust Enable: {s.thrust_enable} | Communication: {c.message} | Fault: {c.fault or 'NONE'}")
        self.measurement_label.setText(f"Measurement State: {c.state.measurement.name} | PC Commanded: {c.commanded:.2f}% | TMS Applied: {s.thrust_command:.2f}%")
        for mode, button in self.mode_buttons.items():
            button.setEnabled(ready and not s.mode_run and not s.thrust_enable and not s.acquire)
        self.enable.setEnabled(ready and s.mode == Mode.MEASUREMENT and not s.mode_run and not s.thrust_enable and c.state.measurement != MeasurementState.FINISHED)
        self.start.setEnabled(ready and c.state.measurement == MeasurementState.READY)
        for button in (self.disable, self.stop, self.emergency):
            button.setEnabled(linked and not c.stopping)
        self.send_thrust.setEnabled(ready and c.state.measurement == MeasurementState.RUNNING and not c.measurement.use_profile)
        self.load_profile_button.setEnabled(not s.mode_run)
        self.profile_on.setEnabled(not s.mode_run)
        self.acquire_start.setEnabled(ready and s.mode == Mode.CALIBRATION and not s.acquire)
        self.acquire_stop.setEnabled(ready and s.acquire)
        self.add_point.setEnabled(ready and s.mode == Mode.CALIBRATION and not s.acquire and bool(c.calibration.samples))
        self.apply_calibration.setEnabled(ready and s.mode == Mode.CALIBRATION and not s.acquire and self.factors is not None)
        self.loss_button.setEnabled(linked and c.transport is not None)
        self.message.setText(c.message)

    def refresh_live(self) -> None:
        c = self.controller
        t = c.telemetry
        if t:
            text = f"Runtime {t.runtime:.3f} s   |   Voltage {t.motor_voltage:.3f} V   |   Current {t.motor_current:.3f} A   |   Measured Thrust {t.load_cell:.4f} N   |   Pressure {t.pressure:.3f} kPa"
            self.sensor_label.setText(text)
            self.measure_sensor.setText(text)
        else:
            text = "Voltage: N/A V | Current: N/A A | Thrust: N/A N | Pressure: N/A kPa — no live telemetry"
            self.sensor_label.setText(text)
            self.measure_sensor.setText(text)
        self.update_state()
        self.sample_count.setText(f"Raw samples acquired: {len(c.calibration.samples)}")
        self.profile_marker.setValue(c.measurement.position)
        channels = tuple(dict.fromkeys(channel for _, channel in self.live_curves))
        times, values = c.visualization.snapshot(channels)
        for curve, channel in self.live_curves:
            curve.setData(times, values[channel])

    def closeEvent(self, event) -> None:
        self.controller.disconnect()
        # Join only after requesting cancellation, bounded I/O timeout prevents indefinite exit.
        thread = self.controller.communication.thread
        if thread:
            thread.join(timeout=0.5)
        self.analysis_manager.pool.waitForDone(1000)
        event.accept()
