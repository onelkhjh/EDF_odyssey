# Requirements

각 행의 Acceptance Criteria가 구현 검증 기준입니다. 실제 하드웨어 관련 기준은 Firmware 규격 확정 후 통합 시험합니다.

| ID | Requirement | Acceptance Criteria |
|---|---|---|
| FR-COM-001 | COM 검색/선택/연결/해제 | 검색 결과 표시, 사용자 baud 입력, 연결 오류 표시 |
| FR-COM-002 | 비동기 Serial/Mock 통신 | GUI thread에서 I/O 없음, 동일 Transport interface |
| FR-COM-003 | Packet 복원 | 분할/연속/손상 packet 처리, 길이 제한 |
| FR-STATE-001 | BOOT/SAFE/STANDBY/CALIBRATION/MEASUREMENT 표시 | STATUS Feedback만 실제 상태 변경; BOOT 진입 명령 거부 |
| FR-STATE-002 | Measurement guard | IDLE→READY→RUNNING→FINISHED 순서; Standby thrust 거부 |
| FR-STBY-001 | 실시간 값/그래프 | runtime s, V, A, load cell, pressure 표시; 가동 버튼 비활성 |
| FR-CAL-001 | 다점 Raw 수집 | 기준 하중 N, sample count, mean, std 표시; 수집 Start/Stop |
| FR-CAL-002 | 선형 회귀 및 적용 | a,b,R², 1/a 표시; Apply 클릭에서만 전송/Feedback 확인 |
| FR-MEAS-001 | 분리된 mode/enable/start | 한 번 클릭으로 동시 가동 불가; Feedback 후 다음 단계 허용 |
| FR-MEAS-002 | Constant thrust | 유한한 0~100% 검증; PC/TMS 명령 비교 |
| FR-MEAS-003 | Stop/Emergency Stop Request | 0%→유한 Feedback 대기→Disable→Stop; 우선 큐 |
| FR-PROF-001 | CSV profile | 필수 열, finite, 증가 time, 2점 이상, 0~100 검증 |
| FR-PROF-002 | Runtime 실행 | TMS runtime 상대 시간 보간, 끝에서 Stop; 미리보기/위치 표시 |
| FR-VIS-001 | 실시간 Plot | bounded ring buffer, GUI refresh와 Mock rate 별도 설정 |
| FR-AN-001 | SD CSV validation | fatal/warning,row,column,description 표시; 원본 보존 |
| FR-AN-002 | 구간/통계 | 선택 시간만 count/mean/min/max/std/RMS 계산 |
| FR-AN-003 | 추력/전기/압력 | 성능, 시간 적분 J/Wh, pressure drop, 안전한 thrust/power |
| FR-AN-004 | 동응답 | 선택된 단일 step rise/fall/settling/overshoot/delay; 불충분 데이터 N/A |
| FR-AN-005 | 비교 | 다중 파일, 시작 runtime 정렬 옵션, 파일명 legend |
| FR-AN-006 | Tracking 단위 검증 | %와 N 직접 오차 계산 금지; 같은 단위 reference만 계산 |
| FR-FB-001 | Command feedback | mode/run/enable/thrust 비교, mismatch/timeout 문자열 표시 |
| FR-SAFE-001 | 연결 상실 | stale state 잠금, 새 thrust 금지, 명확한 경고; 재접속 자동 재가동 없음 |
| FR-SAFE-002 | 최종 안전 책임 | 문서/UI에 TMS 독립 정지 원칙 명시 |
| FR-EXP-001 | Export | processed/range/statistics/summary CSV 및 PNG, 원본 미변경 |
| FR-LOG-001 | 이벤트 로그 | 연결/명령/Feedback/경고/예외 기록, 회전 로그; sample별 기록 기본 off |

## Nonfunctional

Python 3.11+, PySide6, pyqtgraph, pyserial, numpy/pandas/scipy, pytest. 데이터 분석은 worker에서 수행. 모든 위험 명령은 Controller와 Mock 양쪽에서 검증. Hardware 종속 값은 config/TBD; Simulator의 물리 모델은 실제 EDF 특성 주장이 아닙니다.
