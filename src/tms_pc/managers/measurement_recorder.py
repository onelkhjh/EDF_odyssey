import csv
from datetime import datetime
import math
from pathlib import Path
import time


class MeasurementRecorder:
    """Persist every received sample independently of the live plot buffer."""

    def __init__(self, root: str | Path = "recordings") -> None:
        self.root = Path(root)
        self.path = None
        self.stream = None
        self.started = 0.0

    def begin(self, hardware: bool) -> None:
        self.finish()
        folder = self.root / (datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ("_hardware" if hardware else "_mock"))
        folder.mkdir(parents=True)
        self.path = folder / "measurement.csv"
        self.stream = self.path.open("w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.stream)
        self.writer.writerow(["elapsed_s", "runtime", "pc_requested_percent", "thrust_command", "load_cell", "motor_voltage", "motor_current", "pressure", "raw_load_cell", "tms_mode", "mode_run", "thrust_enable", "fault"])
        self.stream.flush()
        self.started = time.monotonic()

    def append(self, telemetry, status, requested: float, fault: str) -> None:
        if self.stream is None:
            return
        self.writer.writerow([time.monotonic() - self.started, telemetry.runtime, requested, status.thrust_command, telemetry.load_cell, telemetry.motor_voltage, telemetry.motor_current, telemetry.pressure, telemetry.raw_load_cell, status.mode.name, int(status.mode_run), int(status.thrust_enable), fault])
        self.stream.flush()

    def finish(self) -> None:
        if self.stream is None:
            return
        self.stream.close()
        self.stream = None
        with self.path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        panels = [("Throttle command (%)", [("pc_requested_percent", "PC requested", "#2563eb"), ("thrust_command", "TMS applied", "#ea580c")]), ("Measured thrust (N)", [("load_cell", "Load cell", "#059669")])]
        parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="700" viewBox="0 0 1100 700">', '<rect width="1100" height="700" fill="white"/>', '<g font-family="sans-serif" font-size="16" fill="#111827">', '<text x="75" y="30">Measurement — elapsed time since Start request</text>']
        duration = max([float(r["elapsed_s"]) for r in rows] + [0.001])
        for panel, (title, channels) in enumerate(panels):
            top = 70 + panel * 310
            series = [(label, color, [(float(r["elapsed_s"]), float(r[key])) for r in rows if math.isfinite(float(r[key]))]) for key, label, color in channels]
            values = [v for _, _, points in series for _, v in points]
            low, high = (0.0, 100.0) if panel == 0 else (min(values + [0.0]), max(values + [1.0]))
            span = high - low or 1.0
            parts.append(f'<text x="75" y="{top}">{title}</text>')
            for tick in range(6):
                y = top + 25 + 210 * tick / 5
                value = high - span * tick / 5
                x = 75 + 950 * tick / 5
                parts.append(f'<path d="M75 {y} H1025" stroke="#e5e7eb"/><text x="5" y="{y + 5}">{value:.3g}</text><text x="{x}" y="{top + 258}">{duration * tick / 5:.2f}</text>')
            for label, color, points in series:
                coords = " ".join(f'{75 + 950 * t / duration:.2f},{top + 25 + 210 * (high - v) / span:.2f}' for t, v in points)
                parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2"/>')
            for index, (label, color, _) in enumerate(series):
                parts.append(f'<text x="{400 + index * 230}" y="{top}" fill="{color}">{label}</text>')
            parts.append(f'<text x="470" y="{top + 285}">Elapsed time (s)</text>')
        if not rows:
            parts.append('<text x="250" y="350">No telemetry received during this Start attempt</text>')
        parts.append('</g></svg>')
        self.path.with_name("thrust_time.svg").write_text("\n".join(parts), encoding="utf-8")
