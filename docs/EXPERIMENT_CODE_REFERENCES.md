# Similar experiment code review

Reviewed 2026-10-03 against the local EDF TMS-PC requirements and analysis implementation. This review distinguishes repository descriptions from source code actually read. No external code has been copied or executed.

## Closest source reviewed

[Automated BLDC Propeller Thrust Stand](https://github.com/aydinonder468/bldc-propeller-thrust-stand) measures propeller thrust with a load cell and uses an Arduino, ESC and PySide6 PC application. It is similar in measurement and experiment supervision; it is not an EDF aerodynamic model or our TMS protocol.

Source files read directly from the main branch:

- [thrust_modeling.py](https://github.com/aydinonder468/bldc-propeller-thrust-stand/blob/main/desktop_app/thrust_modeling.py): `_plateau_points`, `fit_static_model`, `_prepare_dynamic`, `fit_dynamic_models`, `identify`, `response_curves`.
- [thrust_stand_serial.py](https://github.com/aydinonder468/bldc-propeller-thrust-stand/blob/main/desktop_app/telemetry/thrust_stand_serial.py): timestamped telemetry, raw/filtered thrust separation, phase and sequence fields, queued serial commands.

| Code pattern | Local comparison | Proposed application |
|---|---|---|
| Group static samples by phase and PWM, summarize the final 30% with a median | `analysis/thrust.py` summarizes the tail of the entire selected interval | Add explicit plateau segmentation and per-plateau count, duration, thrust statistics and voltage/current/power statistics; do not label a tail as physically settled without checking it |
| Fit a polynomial static PWM-to-N map | Our command is percent, while tracking requires an N reference | Fit only measured command-to-thrust datasets, retain command units and tested domain, report residuals; no implicit percent-to-N conversion |
| Compare first/second-order dynamic models using bounded robust fits and AICc | Our response analysis reports single-step metrics | Candidate later extension after multi-step segmentation and data-quality checks; validate against a separate run before treating a model as predictive |
| Retain raw and filtered thrust, device timestamp, phase and sequence | TMS fields and framing remain unconfirmed | Record those fields only if firmware defines them; preserve original samples and report missing/irregular timestamps |

## Limits found in the reference implementation

- Its second-order simulation caps each elapsed interval at 0.1 s without integrating the remainder. This changes modeled elapsed time for larger gaps; do not reuse that behavior.
- `_prepare_dynamic` checks each timestamp against its immediate predecessor, which does not establish globally increasing retained timestamps after a backward jump. Our validation should reject or explicitly segment clock resets.
- Static model evaluation clips input to the training range. Any analogous feature should expose out-of-range inputs rather than silently presenting a clamped prediction as a measured result.
- `response_curves` initializes the reference at the final step value; the delayed-reference helper extends that same value to negative time. Its plotted step therefore does not reproduce a pre-step baseline for a nonzero delay. Use an explicit baseline when validating delay.
- Reported fit metrics use the fitting samples. They do not by themselves establish independent validation accuracy.
- Serial code assumes an Arduino reset delay, ASCII protocol and 115200 baud, and does not set a write timeout. Those assumptions do not apply to TMS-PC.

## Other relevant repositories

- [iforce2d/thrustTester](https://github.com/iforce2d/thrustTester): repository README reviewed. Arduino + Qt tests thrust, voltage, current and RPM with scripted throttle/thrust/RPM commands and sensor calibration. Relevant for repeatable experiment definitions. Individual C++ source contents were not retrieved in this review; source-level conclusions are pending.
- [vovanol0/uav-motor-thrust-test-stand](https://github.com/vovanol0/uav-motor-thrust-test-stand): repository description reviewed. Load-cell, voltage/current acquisition and Python session logging are relevant. Individual source retrieval failed; no implementation-quality claim is made.

## Recommended implementation order

1. Analyze each command plateau separately, excluding configurable transition time and exposing insufficient data.
2. Export an experiment summary with command units, measured sampling intervals, plateau boundaries and per-plateau electrical/thrust statistics.
3. Add measured static performance curves and compare ascending/descending runs for hysteresis and voltage dependence.
4. Add optional dynamic model identification with synthetic recovery tests, irregular-time integration, explicit delay and independent-run validation.

These are review findings and proposed extensions, not completed implementation. Existing TMS protocol/units decisions remain governed by firmware evidence.
