from dataclasses import dataclass

# UI suggestions only: no firmware baud is selected implicitly.
BAUD_RATE_OPTIONS = (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600)


@dataclass(frozen=True)
class Settings:
    """PC/simulator settings. These are not firmware defaults."""
    feedback_timeout_s: float = 1.0
    connection_timeout_s: float = 2.0
    mock_watchdog_s: float = 3.0
    mock_period_s: float = 0.05
    mock_command_refresh_s: float = 0.5
    calibration_max_samples: int = 10000
    gui_period_ms: int = 50
    worker_period_s: float = 0.01
    serial_read_timeout_s: float = 0.02
    serial_write_timeout_s: float = 0.2
    serial_max_read_bytes: int = 4096
    buffer_samples: int = 2400
    max_payload: int = 512
    thrust_tolerance: float = 0.05
    steady_fraction: float = 0.2
    interval_ratio_warning: float = 3.0
    minimum_power_w: float = 1e-6
    hardware_baud: int | None = None
    hardware_protocol: str | None = None
