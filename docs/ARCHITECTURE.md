# Architecture

Reference-backed refinements: worker-to-Controller events explicitly use queued Qt connections and decorated QObject slots. AnalysisManager result/error delivery and job cleanup run in its owning thread. Plot updates share one bounded NumPy snapshot among page curves. Serial read/write deadlines and maximum chunk size are PC settings. [Sources and validation](REFERENCES.md).

```text
GUI (white, Qt widgets and pyqtgraph)
 └ Application Controller
    ├ State Manager (observed STATUS + transition guards)
    ├ Measurement Manager (profile, bounded stop sequence)
    ├ Calibration Manager (raw acquisition, regression)
    ├ Visualization Manager (bounded samples)
    ├ Analysis Manager (worker, validation/range/exports)
    └ Communication Manager (worker + priority queue + feedback deadlines)
       ├ Packet codec (encoder/stream decoder/checksum strategy)
       ├ Serial Transport
       └ Mock TMS Transport
```

GUI에서는 serial.write를 호출하지 않습니다. QObject signals/queue로 worker 결과를 GUI에 전달합니다. I/O worker가 transport를 단독 소유합니다. GUI refresh는 QTimer로 bounded snapshot만 표시합니다. 분석은 별도 worker에서 실행합니다.

Transport: connect(), disconnect(), send(bytes), read()->bytes. read는 짧은 timeout/nonblocking이어야 합니다. Packet encoding은 protocol profile을 주입합니다. 실제 profile이 없으면 실제 연결을 fail-closed합니다. GUI/Manager는 논리 Packet Type과 typed models만 의존합니다.

명령 송신은 성공이 아닙니다. 각 명령은 기대 STATUS 필드와 deadline을 갖고, Feedback이 일치하면 완료됩니다. 위험 명령은 pending 동안 중복 실행 금지. Stop은 대기 명령과 profile 생성을 취소하고 높은 우선순위로 0%, disable, run false를 직렬 처리합니다. 각각 deadline이 존재합니다. 연결 상실은 활성 시험을 무효화하고 명령 큐를 비웁니다.

통신 큐 취소는 generation 번호를 갱신합니다. worker는 전송 직전에 generation을 다시 확인하여 취소된 이전 명령을 폐기합니다. 이미 전송된 명령은 회수할 수 없으며, 이후 Stop 명령과 TMS 안전 정책이 필요합니다. Disconnect 뒤 늦게 전달된 Qt packet signal은 Controller에서 무시합니다. 실제 Firmware transaction/correlation ID 정책은 TBD입니다.

모든 worker event(packet, connection, sent, warning)는 PC 내부 session ID를 함께 전달합니다. Controller는 현재 session만 수락하여 이전 worker의 늦은 Disconnect가 새 연결을 무효화하지 못하게 합니다. 즉시 재연결은 이전 worker 종료 후 timer에서 비동기로 시작합니다. Session ID는 PC 내부 구현이며 실제 wire protocol ID가 아닙니다.

Mock Constant 운용은 설정된 주기마다 동일 thrust 명령을 갱신하여 simulator watchdog을 유지합니다. Profile 운용은 telemetry runtime마다 보간 명령을 보냅니다. 실제 하드웨어 heartbeat packet/주기는 Firmware 규격 확정 후 Communication adapter에 추가해야 합니다.

단위: Mock의 calibrated load cell N, raw는 별도 값. 실제 펌웨어의 load_cell 의미는 TBD이며 protocol adapter에서 raw/calibrated를 분리해야 합니다. Calibration이 계산한 factor를 TMS가 적용하며 PC는 실시간 센서 변환을 대신 수행하지 않습니다.
