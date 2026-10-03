from collections import deque
import numpy as np
from tms_pc.models.telemetry import Telemetry


class VisualizationManager:
    def __init__(self, max_samples: int) -> None:
        self.samples: deque[tuple[Telemetry, float]] = deque(maxlen=max_samples)

    def append(self, telemetry: Telemetry, command: float) -> None:
        self.samples.append((telemetry, command))

    def channel(self, name: str) -> tuple[list[float], list[float]]:
        return ([t.runtime for t, _ in self.samples], [c if name == "thrust_command" else getattr(t, name) for t, c in self.samples])

    def snapshot(self, channels: tuple[str, ...]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        samples = tuple(self.samples)
        times = np.fromiter((t.runtime for t, _ in samples), dtype=float, count=len(samples))
        values = {name: np.fromiter((c if name == "thrust_command" else getattr(t, name) for t, c in samples), dtype=float, count=len(samples)) for name in channels}
        return times, values
