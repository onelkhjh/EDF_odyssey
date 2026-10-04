# Firmware Protocol

기준: [11_Rocket-Avionics-System](https://github.com/JseoPark/11_Rocket-Avionics-System/tree/bd60824d97615e68efa217bd90a9705edf5408e5/Rocket%20Avionics%20System%20-%20Thrust%20Measurement%20Board), commit `bd60824d97615e68efa217bd90a9705edf5408e5`.
확인한 소스: Core/Inc/user/communication.h, logics.h, board_config.h; Core/Src/user/application.c, measurement.c, pc_communication.c, data_save.c; Drivers/USER_CUSTOM/Source/Software Driver/packet.c.

## Latest changes

2026-10-04: upstream bd60824의 battery_percent 추가를 반영했습니다. PC 명령·Heartbeat·운용 정책은 동일하며 PC report, 추력기 report 및 SD checksum 위치를 갱신했습니다. 관련 테스트 23개가 통과했습니다.

## PC USB VCP framing

PC 연결은 USB CDC/VCP입니다. USART1의 2Mbps 8N1은 TMS↔추력기 연결이며 PC 연결 설정이 아닙니다.
현재 CDC_Control_FS는 line coding을 적용하지 않습니다. GUI Baud는 양의 정수 입력을 요구하지만 USB CDC 전송률을 결정하지 않습니다.

모든 값은 little endian, float32/double64 IEEE-754입니다.

```text
41 42 00 00 | fixed-size payload | uint32 little-endian checksum
```

checksum은 앞의 4바이트와 payload의 byte-sum입니다. CRC가 아닙니다. PC 송신 payload 32B/frame 40B, PC 수신 payload 136B/frame 144B입니다. 길이 필드나 프레임 sequence ID는 없습니다. FirmwareCodec은 분할·연속 수신과 checksum 실패 후 재동기화를 처리합니다. byte-sum은 CRC보다 오류 검출력이 약하며 실제 USB 캡처 검증은 아직 수행하지 않았습니다.

## PC commands

| ID | 동작 | payload 필드 |
|---|---|---|
| 1 | Mode | offset 1 uint8: Safe=0, Boot=1(요청 금지), Standby=2, Calibration=3, Measurement=4 |
| 2 | Start/Stop | offset 2 uint8 running |
| 3 | Calibration Acquire | offset 3 uint8 acquiring |
| 4 | Enable/Disable | offset 4 uint8 thrust_enable |
| 5 | Thrust | offset 8 float32, 0~100% |
| 6 | Calibration | offset 16 double scale_factor, offset 24 double zero_offset |
| 7 | Heartbeat | 추가 필드 없음 |
| 8 | Stop | 출력 차단 후 Standby |

payload offset 0은 ID이며 offset 5~7 padding 및 12~15 reserved는 0으로 송신합니다.
보정 수식은 F=(Raw-zero_offset)/scale_factor입니다. GUI 회귀의 slope(raw/N)를 scale_factor로 보내야 하며 역수(N/raw)는 보내지 않습니다.

PC 상태 응답에는 보정 계수와 명령 ID/ACK가 없습니다. 현재 GUI는 실제 장비 Apply를 비활성화합니다. 인코더는 ID 6을 지원하지만 계수 적용 완료를 확인했다고 주장하지 않습니다. 다른 명령도 상태 일치만 확인하며 명령 correlation을 보장하지 않습니다.

## PC report: 136-byte payload

| offset | 형식 | 내용 |
|---:|---|---|
| 0 | uint8 ×4 | mode, running, acquiring, thrust_enable |
| 4 | float32 | 적용 추력 명령 % |
| 8 | double | runtime s, Measurement Start에서 초기화 |
| 16 | float32 ×4 | motor_voltage, motor_current, loadcell, pressure |
| 32 | uint16 ×5 | RAW loadcell, pressure, current, motor voltage, battery voltage |
| 42 | uint8 ×2 | valid, calibrated |
| 44 | float32 | battery_voltage |
| 48 | uint32 ×3 | counter, fault, thruster_age_ms |
| 60 | 72 bytes | 추력기 report_t 원본 |
| 132 | 4 bytes | padding |

valid=1은 ADC 취득 성공입니다. calibrated bit0은 로드셀, bit1은 아날로그 변환 보정입니다. 미보정 물리량은 펌웨어에서 NaN으로 전송되므로 전체 패킷을 폐기하지 않고 화면에 N/A를 표시합니다. 로드셀 N은 PC에서 기준 하중 N으로 보정할 때 성립합니다. 압력 단위·변환 상수는 board_config.h에서 미확정이므로 kPa로 단정하지 않습니다.

추력기 report_t의 deg_m[4]는 사용자 설명상 서보모터 값입니다. 목표/실제 각도와 단위, deg[4] 및 subsystem_status 비트 의미는 해당 추력기 코드에서 별도 확정이 필요합니다. 72B 원본을 그대로 보존하며 TMS ADC 측정값과 혼합하지 않습니다.

추력기 payload는 offset 60 float32 battery_percent, offset 64 uint8 subsystem_status, offset 65 padding[7]을 사용합니다. PC report 내 절대 offset은 각각 120, 124, 125입니다. ref_time은 음수가 아닌 유한 값, 13개 float는 유한 값, padding[7]은 모두 0이어야 합니다. GUI는 thruster_age_ms <= 500일 때 배터리 잔량을 표시하고 오래된 보고는 N/A로 표시합니다. SD CSV에는 thruster_battery_percent와 72B 원본 hex를 보존합니다. 이전 128B PC payload 및 64B 추력기 payload는 최신 디코더가 수용하지 않습니다.

Fault bits: 0x01 INIT, 0x02 ADC, 0x04 SD, 0x08 PC timeout, 0x10 THRUSTER, 0x20 DEADLINE, 0x40 RX. PC는 Fault 동안 Start/Enable/추력/취득을 차단합니다. 명시적 Mode 요청 후 정상 상태 응답으로 복구합니다.

## Operation and deadlines

- Measurement mode → Enable → thruster_age_ms <= 500 확인 → Start → 별도 Thrust 명령.
- Calibration Acquire는 running=1이 필요합니다. PC는 Acquire Start 요청 시 먼저 Calibration Run을 보내고 STATUS를 받은 뒤 Acquire를 보냅니다.
- ID 8 Stop은 원자적으로 추력 0, Disable, Run/Acquire 해제 후 Standby로 전환합니다. Emergency 요청은 Safe 모드 명령을 사용합니다.
- PC 및 추력기 timeout은 각각 500ms, 메인 루프 deadline은 100ms입니다.
- PC worker는 GUI 작업과 독립적으로 100ms마다 ID 7 Heartbeat를 보냅니다.
- PC STATUS timeout은 기본 300ms이며 Safe 요청을 시도하고 제한 시간 내 응답을 기다린 뒤 재연결을 요구합니다. 요청 송신은 물리적 정지 증명이 아닙니다.
- PC를 닫거나 연결을 끊으면 Heartbeat가 종료됩니다. 현재 종료는 확인된 Stop을 기다리지 않으므로 운용 중에는 Stop Feedback 확인 후 종료해야 합니다. 최종 출력 차단은 펌웨어 timeout에 의존합니다.

## SD binary records

DATAxxxx.BIN은 256MiB 사전 할당 파일이며 512B 기록 단위입니다.
각 섹터는 AB/00 00 + uint32 record_counter + uint32 padding + pc_report_t(136B) + checksum + 360B padding입니다.
유효 프레임은 152B입니다. 미기록 tail을 시험 데이터로 취급하면 안 됩니다.

```powershell
.\.venv\Scripts\python.exe -m tms_pc.communication.firmware_log DATA0000.BIN extracted.csv
```

변환기는 섹터별 header/checksum, 증가 counter, runtime 역행을 검사하며 첫 0 섹터에서 종료합니다. 손상 기록은 위치와 함께 오류 처리하고 기존 출력 파일은 덮어쓰지 않습니다. counter gap과 원본 RAW/flags/fault/추력기 payload를 CSV에 보존합니다. SD 기록 counter와 메인 루프 sample_counter는 서로 다르므로 저장 누락은 sample_counter/runtime도 함께 확인해야 합니다.

출력은 펌웨어 원본 CSV입니다. pressure_firmware_units를 사용하므로 canonical 분석 CSV와 직접 호환되지 않습니다. 압력 단위 및 보정 상태를 확정한 후 명시적 변환이 필요합니다.

## Mock protocol

MockCodec은 기존 TM framing, 논리 enum, CRC32를 유지합니다. FirmwareCodec과 별도로 동작하며 Mock 프레임을 실제 장비에 전송하지 않습니다.
