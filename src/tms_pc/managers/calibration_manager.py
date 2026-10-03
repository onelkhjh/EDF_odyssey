import numpy as np
from tms_pc.models.calibration import CalibrationPoint, CalibrationResult


class CalibrationManager:
    def __init__(self) -> None:
        self.points: list[CalibrationPoint] = []
        self.samples: list[float] = []
        self.reference_n = 0.0

    def add_point(self) -> CalibrationPoint:
        if not self.samples:
            raise ValueError("No raw samples acquired")
        point = CalibrationPoint(self.reference_n, len(self.samples), float(np.mean(self.samples)), float(np.std(self.samples)))
        self.points.append(point)
        self.samples.clear()
        return point

    def fit(self) -> CalibrationResult:
        if len(self.points) < 2:
            raise ValueError("At least two calibration points required")
        x = np.array([p.reference_n for p in self.points])
        y = np.array([p.raw_mean for p in self.points])
        if not np.isfinite(x).all() or not np.isfinite(y).all() or np.ptp(x) == 0:
            raise ValueError("Distinct finite reference loads required")
        slope, offset = np.polyfit(x, y, 1)
        total = float(np.sum((y - y.mean()) ** 2))
        if abs(slope) < 1e-12 or total == 0:
            raise ValueError("Degenerate calibration")
        r2 = 1 - float(np.sum((y - (slope * x + offset)) ** 2)) / total
        return CalibrationResult(float(slope), float(offset), r2)
