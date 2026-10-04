from dataclasses import dataclass


@dataclass(frozen=True)
class Telemetry:
    runtime: float
    motor_voltage: float
    motor_current: float
    load_cell: float
    pressure: float
    raw_load_cell: float
    raw_voltage: float = float("nan")
    raw_current: float = float("nan")
    raw_pressure: float = float("nan")
    raw_battery: float = float("nan")
