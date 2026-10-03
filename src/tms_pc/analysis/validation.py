from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from tms_pc.config.settings import Settings
from tms_pc.models.enums import Mode

REQUIRED = ("runtime", "thrust_command", "motor_voltage", "motor_current", "load_cell", "pressure", "tms_mode", "thrust_enable")
NUMERIC = tuple(c for c in REQUIRED if c != "tms_mode")


@dataclass(frozen=True)
class Issue:
    severity: str
    row: int | None
    column: str
    description: str


@dataclass
class ValidatedData:
    source: Path
    frame: pd.DataFrame
    issues: list[Issue]

    @property
    def fatal(self) -> bool:
        return any(i.severity == "FATAL" for i in self.issues)


def load_csv(path: str | Path, settings: Settings = Settings()) -> ValidatedData:
    source = Path(path).resolve()
    frame = pd.read_csv(source)
    issues: list[Issue] = []
    missing = set(REQUIRED) - set(frame.columns)
    if missing or len(frame) < 2:
        issues.append(Issue("FATAL", None, ",".join(sorted(missing)), "Missing required columns or fewer than 2 samples"))
        return ValidatedData(source, frame, issues)
    invalid = pd.Series(False, index=frame.index)
    for column in NUMERIC + (("thrust_reference_n",) if "thrust_reference_n" in frame else ()):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        bad = ~np.isfinite(frame[column])
        for index in frame.index[bad]:
            issues.append(Issue("WARNING", int(index) + 2, column, "Non-finite/non-numeric value; row excluded"))
        invalid |= bad
    domains = {
        "thrust_command": ~frame.thrust_command.between(0, 100),
        "thrust_enable": ~frame.thrust_enable.isin([0, 1]),
        "tms_mode": ~frame.tms_mode.isin([m.name for m in Mode]),
        "runtime": frame.runtime < 0,
    }
    for column, bad in domains.items():
        for index in frame.index[bad]:
            issues.append(Issue("WARNING", int(index) + 2, column, "Invalid domain; row excluded"))
        invalid |= bad
    clean = frame.loc[~invalid].copy()
    duplicates = clean.runtime.duplicated()
    for index in clean.index[duplicates]:
        issues.append(Issue("WARNING", int(index) + 2, "runtime", "Duplicate timestamp; row excluded"))
    clean = clean.loc[~duplicates].copy()
    if len(clean) < 2 or (np.diff(clean.runtime) <= 0).any():
        issues.append(Issue("FATAL", None, "runtime", "Insufficient samples or unordered runtime"))
    elif len(clean) >= 3:
        intervals = np.diff(clean.runtime)
        median = float(np.median(intervals))
        for index in np.where((intervals > median * settings.interval_ratio_warning) | (intervals < median / settings.interval_ratio_warning))[0]:
            issues.append(Issue("WARNING", int(clean.index[index + 1]) + 2, "runtime", "Irregular sampling interval"))
    return ValidatedData(source, clean.reset_index(drop=True), issues)
