import numpy as np


def statistics(values: np.ndarray) -> dict[str, float | int | None]:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return {key: None for key in ("count", "mean", "min", "max", "std", "rms")}
    return {"count": len(x), "mean": float(x.mean()), "min": float(x.min()), "max": float(x.max()), "std": float(x.std()), "rms": float(np.sqrt(np.mean(x * x)))}
