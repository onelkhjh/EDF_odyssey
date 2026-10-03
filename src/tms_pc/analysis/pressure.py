import pandas as pd


def pressure(frame: pd.DataFrame) -> dict[str, float]:
    p = frame.pressure
    return {"initial_pressure_kpa": float(p.iloc[0]), "maximum_pressure_kpa": float(p.max()), "minimum_pressure_kpa": float(p.min()), "mean_pressure_kpa": float(p.mean()), "pressure_variation_kpa": float(p.max() - p.min()), "pressure_drop_kpa": float(p.iloc[0] - p.iloc[-1])}
