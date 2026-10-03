from tms_pc.models.measurement import ThrustProfile


class MeasurementManager:
    def __init__(self) -> None:
        self.profile: ThrustProfile | None = None
        self.use_profile = False
        self.origin: float | None = None
        self.last_runtime: float | None = None
        self.position = 0.0

    def reset(self) -> None:
        self.origin = self.last_runtime = None
        self.position = 0.0

    def command(self, runtime: float) -> tuple[float, bool]:
        if self.last_runtime is not None and runtime < self.last_runtime:
            raise ValueError("TMS Runtime regressed; Stop requested")
        self.last_runtime = runtime
        if self.origin is None:
            self.origin = runtime
        self.position = runtime - self.origin
        if self.profile is None:
            raise ValueError("No profile loaded")
        return self.profile.value(self.position), self.position >= self.profile.times[-1]
