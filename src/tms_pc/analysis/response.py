import numpy as np
import pandas as pd


def response(frame: pd.DataFrame, step_time: float | None = None, settling_fraction: float = 0.02) -> dict:
    """Analyze one selected step; command % locates time, measured N defines amplitude."""
    empty = {key: None for key in ("rise_time_s", "fall_time_s", "settling_time_s", "peak_n", "overshoot_percent", "steady_n", "delay_s")}
    if len(frame) < 10:
        return {**empty, "reason": "At least 10 samples required"}
    t = frame.runtime.to_numpy(dtype=float)
    y = frame.load_cell.to_numpy(dtype=float)
    if step_time is None:
        changes = np.diff(frame.thrust_command.to_numpy(dtype=float))
        if not np.any(np.abs(changes) > 1e-6):
            return {**empty, "reason": "No command step detected"}
        index = int(np.argmax(np.abs(changes))) + 1
        step_time = float(t[index])
    index = int(np.searchsorted(t, step_time))
    if index < 2 or index >= len(t) - 4:
        return {**empty, "reason": "Need baseline and post-step samples"}
    baseline = float(np.mean(y[:index]))
    tail_count = max(2, len(y[index:]) // 5)
    final = float(np.mean(y[-tail_count:]))
    amplitude = final - baseline
    if abs(amplitude) < 1e-9:
        return {**empty, "reason": "No measured response amplitude"}
    normalized = (y[index:] - baseline) / amplitude
    tt = t[index:]

    def crossing(level: float) -> float | None:
        hits = np.where(normalized >= level)[0]
        if not len(hits):
            return None
        k = int(hits[0])
        if k == 0:
            return float(tt[0])
        x0, x1 = normalized[k - 1], normalized[k]
        return float(tt[k - 1] + (level - x0) / (x1 - x0) * (tt[k] - tt[k - 1]))

    t10, t90 = crossing(0.1), crossing(0.9)
    outside = np.where(np.abs(normalized - 1) > settling_fraction)[0]
    settled_index = int(outside[-1] + 1) if len(outside) else 0
    settling = float(tt[settled_index] - step_time) if settled_index < len(tt) - 1 else None
    duration = None if t10 is None or t90 is None else t90 - t10
    return {"rise_time_s": duration if amplitude > 0 else None, "fall_time_s": duration if amplitude < 0 else None, "settling_time_s": settling, "peak_n": float(np.max(y[index:]) if amplitude > 0 else np.min(y[index:])), "overshoot_percent": max(0.0, float(np.max(normalized) - 1) * 100), "steady_n": final, "delay_s": None if t10 is None else t10 - step_time, "reason": "Single selected step; final tail used as steady state"}
