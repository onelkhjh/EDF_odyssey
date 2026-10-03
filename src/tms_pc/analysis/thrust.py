import numpy as np
import pandas as pd
from tms_pc.config.settings import Settings


def thrust(frame: pd.DataFrame, settings: Settings = Settings()) -> dict[str, float | None]:
    values = frame.load_cell.to_numpy()
    steady = frame.runtime >= frame.runtime.iloc[-1] - (frame.runtime.iloc[-1] - frame.runtime.iloc[0]) * settings.steady_fraction
    result = {"maximum_thrust_n": float(values.max()), "minimum_thrust_n": float(values.min()), "mean_thrust_n": float(values.mean()), "steady_thrust_n": float(frame.loc[steady, "load_cell"].mean()), "thrust_std_n": float(values.std()), "thrust_rms_n": float(np.sqrt(np.mean(values ** 2))), "thrust_peak_to_peak_n": float(np.ptp(values))}
    result.update({key: None for key in ("tracking_mae_n", "tracking_rmse_n", "tracking_max_error_n", "tracking_steady_error_n")})
    if "thrust_reference_n" in frame:
        error = frame.thrust_reference_n - frame.load_cell
        result.update(tracking_mae_n=float(error.abs().mean()), tracking_rmse_n=float(np.sqrt(np.mean(error ** 2))), tracking_max_error_n=float(error.abs().max()), tracking_steady_error_n=float(error[steady].mean()))
    return result
