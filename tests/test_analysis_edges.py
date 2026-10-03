import numpy as np
import pandas as pd
import pytest
from tms_pc.analysis.response import response
from tms_pc.analysis.validation import load_csv
from tms_pc.analysis.electrical import process
from tms_pc.analysis.thrust import thrust
from tms_pc.analysis.pressure import pressure


@pytest.mark.parametrize("falling", [False, True])
def test_single_step_response(falling):
    t = np.arange(0, 8, .01)
    response_n = np.where(t >= 1, 10 * (1 - np.exp(-np.maximum(t - 1, 0) / .3)), 0)
    measured = 10 - response_n if falling else response_n
    frame = pd.DataFrame({"runtime": t, "load_cell": measured, "thrust_command": np.where(t < 1, 50 if falling else 0, 0 if falling else 50)})
    result = response(frame)
    key = "fall_time_s" if falling else "rise_time_s"
    assert result[key] == pytest.approx(.3 * np.log(9), abs=.02)
    assert result["settling_time_s"] == pytest.approx(-.3 * np.log(.02), abs=.03)
    assert result["overshoot_percent"] < .01


def test_validation_reports_rows_and_keeps_usable_data(tmp_path):
    path = tmp_path / "issues.csv"
    path.write_text("runtime,thrust_command,motor_voltage,motor_current,load_cell,pressure,tms_mode,thrust_enable\n0,0,24,1,0,101,STANDBY,0\n1,0,NaN,1,0,101,STANDBY,0\n2,0,24,1,0,101,STANDBY,0\n2,0,24,1,0,101,STANDBY,0\n3,0,24,1,0,101,STANDBY,0\n")
    data = load_csv(path)
    assert not data.fatal
    assert len(data.frame) == 3
    assert any(i.row == 3 and i.column == "motor_voltage" for i in data.issues)
    assert any(i.row == 5 and "Duplicate" in i.description for i in data.issues)
    assert "NaN" in path.read_text()


def test_units_and_zero_power():
    frame = pd.DataFrame({"runtime": [0, 1, 2], "motor_voltage": [0, 24, 24], "motor_current": [0, 1, 1], "load_cell": [1, 2, 3], "pressure": [101, 100, 99], "thrust_reference_n": [1, 2, 4]})
    assert np.isnan(process(frame).thrust_per_w.iloc[0])
    assert thrust(frame)["tracking_rmse_n"] == pytest.approx(np.sqrt(1 / 3))
    assert pressure(frame)["pressure_drop_kpa"] == 2
