import numpy as np
import pandas as pd
from tms_pc.config.settings import Settings


def electrical(frame: pd.DataFrame) -> dict[str, float]:
    power = frame.motor_voltage.to_numpy() * frame.motor_current.to_numpy()
    energy = float(np.trapezoid(power, frame.runtime.to_numpy()))
    return {"mean_voltage_v": float(frame.motor_voltage.mean()), "minimum_voltage_v": float(frame.motor_voltage.min()), "maximum_current_a": float(frame.motor_current.max()), "mean_current_a": float(frame.motor_current.mean()), "maximum_power_w": float(power.max()), "mean_power_w": float(power.mean()), "energy_j": energy, "energy_wh": energy / 3600}


def process(frame: pd.DataFrame, settings: Settings = Settings()) -> pd.DataFrame:
    result = frame.copy()
    result["power_w"] = result.motor_voltage * result.motor_current
    denominator = result.power_w.where(result.power_w.abs() > settings.minimum_power_w)
    result["thrust_per_w"] = result.load_cell / denominator
    return result
