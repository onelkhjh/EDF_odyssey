# GUI Design

White background, dark text, blue navigation, red Stop/Emergency buttons with explicit strings. Color is supplementary.

Top: transport/COM, editable baud (hardware default TBD), refresh/connect/disconnect, connection, TMS mode/run/enable, communication status, fault/warning.

Baud (bit/s) 콤보박스는 9600/19200/38400/57600/115200/230400/460800/921600 후보와 직접 입력을 제공합니다. 초기 선택은 비어 있으며 Firmware 기본값을 가정하지 않습니다. 명시적인 Settings.hardware_baud가 있으면 표시합니다. 연결 시 양의 정수를 검증하고 연결 중에는 Port/Baud 변경을 잠급니다. Mock은 Baud를 사용하지 않습니다. 실제 Serial 연결은 전체 protocol 확정 전 차단되어 있습니다.
Left: Standby, Calibration, Measurement, Analysis. Navigation never changes TMS mode. Explicit mode entry buttons perform mode requests.
Bottom: persistent status/warning and `PC is not a safety system; final motor stop belongs to TMS`.

Standby: runtime s, V,A,N,kPa and five-channel plots; all propulsion controls disabled.
Calibration: reference N (kg conversion not implicit), acquire start/stop, add raw samples to table, regression a,b,scale,R² and plot, explicit Apply to TMS.
Measurement: mode entry, separate Enable/Start, Disable, Stop, Emergency Stop Request. Constant % spinner, CSV load/preview/current marker, PC commanded vs applied %, measured N, sensor values and state.
Analysis: multi-file selection, validation table/messages, start/end seconds, align-start checkbox, channel selection, time plots/scatter, statistics/summary/dynamic result, exports. File loading/calculation/export executes outside UI thread. Manual dynamic selection uses entered range; auto detection may choose one dominant step and must report assumptions.

Buttons reflect observed state and pending operations. Errors are shown as understandable text and logged with stack details.

Disconnect 시 기존 sensor 값/그래프를 제거하고 N/A를 표시합니다. Reconnect 중에는 새 Telemetry를 기다린다는 상태를 표시하고, 이전 worker 종료를 GUI thread에서 대기하지 않습니다. 센서 문자열은 작은 창에서도 줄바꿈됩니다.
