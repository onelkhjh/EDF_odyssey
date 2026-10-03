from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ThrustProfile:
    times: np.ndarray
    commands: np.ndarray
    interpolation: str = "linear"

    @classmethod
    def load(cls, path: str | Path) -> "ThrustProfile":
        frame = pd.read_csv(path)
        if not {"time_s", "thrust_percent"}.issubset(frame.columns):
            raise ValueError("Profile requires time_s and thrust_percent")
        times = frame.time_s.to_numpy(dtype=float)
        values = frame.thrust_percent.to_numpy(dtype=float)
        if len(times) < 2 or not np.isfinite(times).all() or not np.isfinite(values).all():
            raise ValueError("Profile requires at least two finite points")
        if times[0] < 0 or not (np.diff(times) > 0).all() or not ((values >= 0) & (values <= 100)).all():
            raise ValueError("Profile time must increase and thrust must be 0–100%")
        return cls(times, values)

    def value(self, time_s: float) -> float:
        if not np.isfinite(time_s):
            raise ValueError("Runtime must be finite")
        if self.interpolation == "zoh":
            index = int(np.clip(np.searchsorted(self.times, time_s, side="right") - 1, 0, len(self.times) - 1))
            return float(self.commands[index])
        if self.interpolation != "linear":
            raise ValueError("Unknown interpolation")
        return float(np.interp(time_s, self.times, self.commands))
