from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationPoint:
    reference_n: float
    samples: int
    raw_mean: float
    raw_std: float


@dataclass(frozen=True)
class CalibrationResult:
    slope: float
    offset: float
    r_squared: float

    @property
    def scale_factor(self) -> float:
        return 1.0 / self.slope
