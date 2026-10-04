from collections import deque
import numpy as np
from tms_pc.models.telemetry import Telemetry


class VisualizationManager:
    def __init__(self, max_samples: int) -> None:
        self.samples: deque[tuple[Telemetry, float]] = deque(maxlen=max_samples)
        self.plot_times: deque[float] = deque(maxlen=max_samples)

    def append(self, telemetry: Telemetry, command: float, plot_time: float | None = None) -> None:
        if not self.samples:
            self.plot_times.clear()
        self.samples.append((telemetry, command))
        self.plot_times.append(telemetry.runtime if plot_time is None else plot_time)

    def channel(self, name: str) -> tuple[list[float], list[float]]:
        return ([t.runtime for t, _ in self.samples], [c if name == "thrust_command" else getattr(t, name) for t, c in self.samples])

    def snapshot(self, channels: tuple[str, ...]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        samples = tuple(self.samples)
        times = np.asarray(tuple(self.plot_times), dtype=float) if samples else np.array([], dtype=float)
        values = {name: np.fromiter((c if name == "thrust_command" else getattr(t, name) for t, c in samples), dtype=float, count=len(samples)) for name in channels}
        return times, values
