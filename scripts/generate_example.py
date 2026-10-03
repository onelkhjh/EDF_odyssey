"""Generate repeatable simulator-only analysis fixture."""
from pathlib import Path
import numpy as np
import pandas as pd

t = np.arange(0, 10.001, 0.05)
command = np.where((t >= 2) & (t < 7), 50.0, 0.0)
force = np.zeros_like(t)
for i in range(1, len(t)):
    force[i] = force[i - 1] + (command[i] * 0.2 - force[i - 1]) * (1 - np.exp(-0.05 / 0.3))
frame = pd.DataFrame({"runtime": t, "thrust_command": command, "motor_voltage": 24 - force * 0.06, "motor_current": 0.2 + force * 1.4, "load_cell": force, "pressure": 101.3 - force * 0.04, "tms_mode": "MEASUREMENT", "thrust_enable": 1, "raw_load_cell": force * 1000 + 100})
frame.to_csv(Path(__file__).resolve().parents[1] / "examples/sample_log.csv", index=False)
