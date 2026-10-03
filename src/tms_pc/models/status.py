from dataclasses import dataclass
from tms_pc.models.enums import Mode


@dataclass(frozen=True)
class Status:
    mode: Mode = Mode.BOOT
    mode_run: bool = False
    thrust_enable: bool = False
    thrust_command: float = 0.0
    acquire: bool = False
    slope: float = 1000.0  # Simulator raw/N, not hardware default
    offset: float = 100.0  # Simulator raw counts
