# Protocol

## Hardware profile — TBD

Binary packet: SOF | Packet ID | Payload Length | Payload | CRC.

| Parameter | Hardware value |
|---|---|
| SOF / Packet ID numbers | TBD |
| CRC algorithm / polynomial / width / init / reflection / xor | TBD |
| Byte order / other packets' field widths / alignment / padding | TBD; report_t layout below provided by user |
| Baud / telemetry sampling frequency | TBD |
| Firmware ACK / correlation / feedback cadence | TBD |
| timeout limits | PC configurable; Firmware safety limits TBD |

아래는 논리 schema이며 실제 wire schema 확정이 아닙니다. `struct` 기반 adapter가 변경 지점입니다. 실제 protocol 설정 없이는 Serial 운용을 허용하지 않습니다.

| Packet | Field | Proposed type | Unit / meaning |
|---|---|---|---|
| COMMAND_MODE | mode | uint8 | SAFE/STANDBY/CALIBRATION/MEASUREMENT |
| COMMAND_MODE_RUN | mode_run | uint8 | bool |
| COMMAND_CALIBRATION_ACQUIRE | acquire | uint8 | bool |
| COMMAND_THRUST_ENABLE | thrust_enable | uint8 | bool |
| COMMAND_THRUST | thrust_command | float32 | % |
| COMMAND_CALIBRATION_FACTOR | slope,offset | float64 x2 | raw/N, raw; equivalent scale=1/slope |
| STATUS | mode,mode_run,thrust_enable,acquire | uint8 | observed state |
| STATUS | thrust_command | float32 | applied % |
| STATUS | slope,offset | float64 | factor feedback; Hardware support TBD |
| TELEMETRY | runtime | float64 | TMS s |
| TELEMETRY | motor_voltage,motor_current | float32 | V,A |
| TELEMETRY | load_cell,pressure | float32 | N,kPa for Mock; Hardware TBD |
| TELEMETRY | raw_load_cell | float64 | raw acquisition; Hardware representation TBD |
| FAULT | message | variable UTF-8 | Mock diagnostic; Hardware fault code TBD |

## User-supplied TX report_t — 64 bytes

Firmware TX (PC RX) report payload supplied by user. `packed` removes implicit alignment; `padding[3]` is an explicit field. Report layout totals 64 bytes if double is 8 bytes and float is 4 bytes. Firmware should verify `sizeof(report_t)==64` with a static assertion. No SOF, length or CRC field appears in this structure; external framing is still TBD.

| Field | Byte offset (zero based) | Size | Meaning / unit |
|---|---:|---:|---|
| packet_counter | 0 | 4 | uint32 sequence counter; reset/wrap policy TBD |
| ref_time | 4 | 8 | double; runtime origin and time unit TBD |
| thrust | 12 | 4 | float; measured/command and N/kgf/%/raw semantics TBD |
| deg[4] | 16 | 16 | four float values; angle meaning/unit TBD |
| voltage_edf | 32 | 4 | float; EDF voltage, unit/scaling TBD |
| current_edf | 36 | 4 | float; EDF current, unit/scaling TBD |
| deg_m[4] | 40 | 16 | four float values; meaning/unit TBD |
| logic_voltage | 56 | 4 | float; logic voltage, unit/scaling TBD |
| subsystem_status | 60 | 1 | uint8; bit definitions TBD; preserve raw byte |
| padding[3] | 61 | 3 | explicit bytes; values unspecified, preserve |

`ReportDecoder(byte_order=...)` decodes an already-framed exact 64-byte payload using Python `struct` format `Id12fB3s` with an explicitly selected `<` or `>` prefix. No native alignment and no default byte order. Decoder assumes standard IEEE-754 binary32/binary64 wire representation; Firmware confirmation required. Nonfinite float fields are rejected and padding is not assumed zero.

Report data is held in a separate typed `HardwareReport` model. It is not silently mapped into canonical Telemetry because thrust/time/sensor units are unconfirmed. This report lacks pressure, raw calibration samples, explicit mode/run/enable and applied-command feedback; these may exist in other packets or status bits, but this cannot be inferred. Real COM operation remains blocked until framing, units and control/feedback policies are specified. USB read calls may split/combine payloads; treating each read as one report or blindly chunking 64 bytes without synchronization is unsafe.

## Simulator-only protocol

Mock profile uses explicit test-only SOF `TM`, little endian, uint8 packet ID, uint16 length, packed struct payload and uint32 zlib CRC32. IDs are generated from the logical enum only for this test profile. These values never default to hardware. CRC strategy is replaceable; corruption tests validate deterministic test framing, not Firmware compliance.

Streaming decoder accepts fragmented/concatenated packets, caps payload size, resynchronizes after corruption and emits diagnostics. Only valid STATUS/TELEMETRY/FAULT count as link activity. Finite numbers and enum/boolean domains are validated before use. Disconnect resets decoder and pending expectations.
