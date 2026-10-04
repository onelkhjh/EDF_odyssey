# TODO / Decisions / Phase Ledger

## 2026-10-04 Upstream update bd60824

기준 commit: bd60824d97615e68efa217bd90a9705edf5408e5. 추력기 battery_percent 추가와 72B payload, 136B PC report/144B frame, 152B SD frame/360B sector padding을 반영했다. 디코더·SD 변환·GUI 배터리 잔량 및 관련 문서를 갱신했다. 변경된 디코더·SD 변환 테스트 23개가 통과했다. 이전 크기는 자동 혼용하지 않는다. 명령·Heartbeat·timeout 정책은 변경되지 않았다.


## 2026-10-04 Initial firmware alignment history

기준 upstream commit: 57b17c7fbd167146f64a32b728f3ac71b665c8aa, Rocket Avionics System - Thrust Measurement Board.
실제 USB VCP용 FirmwareCodec과 연결을 추가했다. AB/00 00 byte-sum framing, 32B command, 128B report, 명시적 mode 값, 100ms Heartbeat, fault 잠금과 300ms STATUS timeout, Calibration Run→Acquire, ID 8 Stop→Standby를 반영했다.
512B SD sector 변환 CLI를 추가했고 RAW/flags/fault/추력기 payload를 보존한다. 압력 단위가 미확정이므로 canonical CSV 자동 변환은 제공하지 않는다.
계수 echo/ACK가 없어 실제 GUI Apply는 비활성화한다. 보정 확인, 명령 correlation, 종료 전 Stop 확인, 실제 USB 캡처/장비 테스트, 아날로그 단위 확인이 남아 있다. 아래 이전 기록의 Serial 차단/TBD 내용은 이 변경 이전 이력이다. 현재 규격은 PROTOCOL.md 참조.

검증: 50개 pytest 통과. 명령 golden bytes, 분할/연속 수신, 손상 checksum 복구, NaN/보정 flag, 512B SD counter/tail/손상, Fault 운용 차단, Calibration Run→Acquire, worker Heartbeat 및 STATUS timeout과 기존 Mock 테스트를 포함한다. 실제 장비 검증 결과는 아니다.

## Latest reference review

Official pySerial, Qt for Python, pyqtgraph and Python struct sources reviewed and recorded in [REFERENCES.md](REFERENCES.md). Implemented configurable serial deadlines/chunk limits and loop:// backend tests, explicit queued QObject slots and owner-thread analysis job cleanup, shared bounded NumPy plot snapshots and display clipping/downsampling. Resolved curve-parent initialization failure found by GUI test. Full suite: 42 passed in 8.41s. Sensor units/framing/CRC are still TBD; real serial GUI remains blocked. Production UART parity/data/stop bits and DTR/RTS/flow-control behavior need Firmware confirmation.

## Completed

Phase 1: requirements, architecture, protocol, state, UI, data, safety and tests documented before implementation. Cross-review: STATUS-only observed state, N calibration, %/N tracking separation, bounded stop, no real protocol defaults consistently specified.

## Pending

Phases 2–13: initial implementation files created (models/state, mock framing/transport, threaded communication, controller, white GUI, calibration, measurement/profile, bounded plots, async analysis and CSV/PNG exports).

Phase 14: initial tests plus asynchronous operation/GUI and analysis edge tests implemented. 2026-10-03: **19 passed in 4.49s** with `.venv\Scripts\python.exe -m pytest -q`.

Phase 15: README and design documents updated to verified Mock status and remaining limitations.

## Verification record

2026-10-02: verification deferred at user request. Initial example generation failed without pandas; example was created without external dependencies.

2026-10-03: user requested next step. Created `.venv`, installed requirements (network approval), ran automated tests and offscreen `python -m tms_pc.main --mock --smoke-seconds 3` (exit 0). Test setup initially required creating the requested artifacts parent directory; resolved. GUI tests exercise live labels, background CSV analysis, window capture and graph PNG export. Rendered artifacts were generated; visual inspection tool returned access denied, so visual QA is not claimed.

Resolved: Constant simulator watchdog renewal, bounded calibration sample storage, disabled READY state reset, cancellation generation before worker send, disconnect ignores late packets, repeated connect preserves active transport reference. Added tests for Feedback timeout/bounded Stop, loss, profile completion, dynamic rising/falling steps and zero-power division.

Next: manual GUI interaction and visual layout QA; packaging build; protocol adapter once Firmware specification is available. Hardware safety remains unverified.

## Current limitations

Baud selection UI added: editable preset combo, explicit bit/s label, no assumed default, custom positive integer validation and lock while connected. Selection feeds the existing connect_serial(port, baud) boundary; actual connection remains blocked pending protocol review. Mock ignores baud.

2026-10-03 reconnect fix: communication events now include a session ID; old disconnect/status/sent/warning events cannot affect a newer connection. Immediate reconnect waits asynchronously for the old worker to finish. Disconnect clears stale telemetry and plots; sensor labels show N/A until fresh telemetry arrives. Labels wrap on narrow layouts. Verified 23 tests passing, including three repeated GUI Disconnect/Connect cycles with refreshed Voltage and graph data. Native desktop automation remains unavailable (Computer Use native pipe unavailable); Qt widget click-event tests were used instead.

- Real Serial connection intentionally blocked while protocol is TBD.
- Auto dynamic analysis chooses one dominant command change; multi-step segmentation is deferred.
- Calibration raw sample list is capped by `calibration_max_samples` (default 10000); reaching the cap requests acquisition stop.
- Graph PNG rendering runs on GUI thread because Qt graphics items belong to it; larger exports should capture image then write on a worker.
- Real communication heartbeat policy is TBD. Mock Constant runs explicitly resend the observed requested thrust every `mock_command_refresh_s` (default 0.5 s), subject to guards and Feedback, to renew the simulator watchdog. This is not a Firmware heartbeat specification.
- Feedback timeout and late packets after disconnect have regression tests. Real packet correlation, stale feedback across reconnection and exact Firmware ACK policy still need integration validation; observed STATUS equality cannot prove command correlation.

## Hardware TBD

User supplied packed TX `report_t`: exact proposed 64-byte layout documented in PROTOCOL.md. A payload-only ReportDecoder and HardwareReport model added. Endian, IEEE representation, time/thrust/angle/voltage/current semantics and subsystem_status bits remain unconfirmed. Framing/CRC and PC TX command definitions are still missing. No implicit Telemetry mapping or real serial enablement.

Report decoder targeted tests: 11 passed in 0.04s. Test data is synthetic, independently packed by byte offset; real packet capture verification pending.

SOF, IDs, field formats, endian/padding, CRC full parameters, baud, sampling, runtime reset semantics, ACK/correlation and factor feedback policy, raw sample packet, sensor units, Firmware safety timeout and mode-transition policy.

## Implementation assumptions

Mock-only struct protocol and CRC32; no actual device compatibility claim. Calibration uses N; TMS applies factors. Analysis canonical load_cell is N. Profile runtime is relative to first running telemetry. Re-entry is required after completed session. Fixed PC timeout/GUI refresh/Mock rate are editable PC settings, not Firmware specification.
