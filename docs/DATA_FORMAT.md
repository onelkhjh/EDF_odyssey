# Data Format

UTF-8 CSV header, decimal point, no implicit unit conversion. Original CSV never modified.

| Canonical column | Unit | Required |
|---|---|---|
| runtime | s, TMS monotonic | yes |
| thrust_command | % [0,100] applied | yes |
| motor_voltage | V | yes |
| motor_current | A | yes |
| load_cell | N calibrated in canonical files | yes |
| pressure | kPa | yes |
| tms_mode | enum name | yes |
| thrust_enable | 0 or 1 | yes |
| raw_load_cell | raw counts | optional |
| thrust_reference_n | N reference | optional |

Hardware SD CSV mapping/units TBD. Import requires explicit canonical units; renaming unknown raw values to calibrated N is prohibited. Examples are Simulator data only.

Profile: `time_s,thrust_percent`, at least two finite rows, strictly increasing nonnegative time, [0,100] percent; linear interpolation, endpoints held until completion, completion triggers Stop. Zero-order hold supported as strategy.

Validation: absent columns, empty/insufficient usable numeric rows, unordered runtime are fatal. NaN/inf/bad numeric rows are reported by CSV line (header=1) and excluded from processed copy when enough data remains; duplicate timestamps reported/excluded explicitly. Irregular intervals warning uses median interval ratio (configurable). Invalid state/enable/range values reported. Exclusion report accompanies analysis.

Stats use population std (ddof=0), RMS=sqrt(mean(x²)); energy uses trapezoidal integration with actual timestamps. Selected steady state defaults to final 20% of selected duration (analysis setting, not hardware sampling). Tracking requires thrust_reference_n; otherwise N/A (command % vs N is transfer characteristic only). Dynamic step analysis uses user-selected single transition and 10/90% crossings, 2% settling band; noisy/insufficient data returns N/A with reason. Pressure drop = initial - final; variation=max-min.

Exports: processed data with power_w and thrust_per_w (NaN at near-zero power), selected range, long-form statistics, key/value summary, graph PNG. Output names use source stem/timestamp; source overwrite refused.
