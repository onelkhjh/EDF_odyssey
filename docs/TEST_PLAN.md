# Test Plan

Latest full suite: 2026-10-03, 42 passed in 8.41s. Reference-backed improvements add actual pySerial loopback stream tests, finite positive serial timeout validation, analysis success/failure owner-thread delivery and cleanup, and bounded plot snapshot checks. Hardware and native desktop input automation remain unverified.

Phase order: 1 documents, 2 skeleton, 3 models/state, 4 packet/transport, 5 Mock, 6 shell, 7 standby, 8 calibration, 9 measurement, 10 profile, 11 plots, 12 analysis, 13 export, 14 pytest, 15 docs.

Automated pytest:
- codec roundtrip, split/concatenated input, invalid ID/length, CRC corruption/resync, finite/schema checks.
- guards: standby→running forbidden; idle start refused; separate enable/start; pending/lost inhibits thrust.
- calibration R=1000F+100, slope/intercept/R², insufficient/degenerate points.
- linear/ZOH profile, NaN/nonmonotonic/range rejected, TMS runtime execution.
- statistics mean/std/RMS, constant and irregular-time energy, unit-aware tracking.
- dynamic rising/falling step, insufficient/no-step N/A, pressure and divide-by-zero.
- Mock feedback and full measurement start/stop, loss/reconnect, timeout and priority Stop.
- offscreen GUI startup and white theme; async CSV analysis and export smoke.

Manual GUI: mock connect→standby sensor updates→calibration→measurement→enable→start→command→stop→standby; CSV profile preview/play; loss lock; sample CSV load/range/compare/export.

Hardware-only deferred: COM device integration, actual framing/CRC/feedback, raw calibration semantics, Firmware timeout independent stop, emergency switch, motor limits and sensor validation.

Record actual commands/results in TODO/README after execution. Never claim manual or hardware checks that were not performed.

## report_t decoder verification

User-supplied packed report_t payload decoder: `.venv\Scripts\python.exe -m pytest tests/test_report_decoder.py -q` passed 11 tests in 0.04s. Fixtures independently pack documented offsets for little/big endian, preserve nonzero padding and uint32 counter maximum, and reject invalid length/nonfinite values/implicit endian. Synthetic fixtures only; not Firmware captures. GUI/reconnect suite previously passed 23 tests; full suite after this isolated addition not rerun.

## Executed — 2026-10-03

`.venv\Scripts\python.exe -m pytest -q`: 19 passed in 4.49s.

`QT_QPA_PLATFORM=offscreen` with `.venv\Scripts\python.exe -m tms_pc.main --mock --smoke-seconds 3`: exit 0; application start, Mock connection, disconnect logged. GUI test captured the analysis window and exported graph PNG, but manual visual inspection and native desktop interaction were not performed.

The final suite covers single-step rising/falling response, NaN/duplicate-row diagnostics, unit-aware tracking, zero power, full asynchronous Measurement/Stop, Constant watchdog renewal, profile completion, calibration Feedback/sample cap, connection loss, ignored late packets and missing-feedback bounded Stop.
