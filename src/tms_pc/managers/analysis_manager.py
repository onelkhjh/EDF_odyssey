from dataclasses import dataclass
from pathlib import Path
import logging
from PySide6.QtCore import QObject, Signal, Slot, Qt, QRunnable, QThreadPool
import pandas as pd
from tms_pc.analysis.validation import ValidatedData, load_csv
from tms_pc.analysis.statistics import statistics
from tms_pc.analysis.electrical import process, electrical
from tms_pc.analysis.thrust import thrust
from tms_pc.analysis.pressure import pressure
from tms_pc.analysis.response import response


@dataclass
class AnalysisResult:
    dataset: ValidatedData
    processed: pd.DataFrame
    selected: pd.DataFrame
    statistics: pd.DataFrame
    summary: dict
    dynamic: dict


def analyze(dataset: ValidatedData, start: float | None = None, end: float | None = None, step_time: float | None = None) -> AnalysisResult:
    if dataset.fatal:
        raise ValueError("Fatal CSV validation errors: " + "; ".join(i.description for i in dataset.issues if i.severity == "FATAL"))
    processed = process(dataset.frame)
    start = float(processed.runtime.iloc[0]) if start is None else start
    end = float(processed.runtime.iloc[-1]) if end is None else end
    if start >= end:
        raise ValueError("Start Time must precede End Time")
    selected = processed.loc[processed.runtime.between(start, end)].copy()
    if len(selected) < 2:
        raise ValueError("Selected range requires at least two samples")
    rows = [{"channel": column, **statistics(selected[column].to_numpy())} for column in ("load_cell", "motor_voltage", "motor_current", "pressure", "power_w")]
    summary = {"duration_s": float(selected.runtime.iloc[-1] - selected.runtime.iloc[0]), **thrust(selected), **electrical(selected), **pressure(selected)}
    return AnalysisResult(dataset, processed, selected, pd.DataFrame(rows), summary, response(selected, step_time))


class JobSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, function) -> None:
        super().__init__()
        self.function = function
        self.signals = JobSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(self.function())
        except Exception as exc:
            logging.getLogger(__name__).exception("Analysis/export error")
            self.signals.failed.emit(str(exc))


class AnalysisManager(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.pool = QThreadPool(self)
        self.jobs: list[Job] = []

    def submit(self, function) -> None:
        job = Job(function)
        self.jobs.append(job)
        job.signals.done.connect(self._job_done, Qt.ConnectionType.QueuedConnection)
        job.signals.failed.connect(self._job_failed, Qt.ConnectionType.QueuedConnection)
        self.pool.start(job)

    def _release_job(self) -> None:
        sender = self.sender()
        self.jobs[:] = [job for job in self.jobs if job.signals is not sender]

    @Slot(object)
    def _job_done(self, result: object) -> None:
        self._release_job()
        self.completed.emit(result)

    @Slot(str)
    def _job_failed(self, message: str) -> None:
        self._release_job()
        self.failed.emit(message)

    def load(self, paths: list[str]) -> None:
        self.submit(lambda: [load_csv(path) for path in paths])


def export_result(result: AnalysisResult, directory: str | Path) -> list[Path]:
    from datetime import datetime
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stem = result.dataset.source.stem + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    frames = {"processed": result.processed, "range": result.selected, "statistics": result.statistics, "summary": pd.DataFrame([result.summary]), "validation": pd.DataFrame([vars(i) for i in result.dataset.issues])}
    paths = []
    for name, frame in frames.items():
        target = directory / f"{stem}_{name}.csv"
        if target.resolve() == result.dataset.source:
            raise ValueError("Cannot overwrite source CSV")
        frame.to_csv(target, index=False, encoding="utf-8-sig", mode="x")
        paths.append(target)
    return paths
