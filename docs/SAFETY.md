# Safety

1. PC is not an actual safety system. OS, USB, scheduling and application failures are possible.
2. Upstream TMS firmware at bd60824 defines PC/thruster timeouts of 500ms and loop deadline of 100ms, with independent output shutdown and Safe fault transition. PC sends heartbeat every 100ms. These behaviors still require hardware verification.
3. PC guard prevents unsafe-state commands. Only STATUS feedback authorizes subsequent steps. BOOT is never requested.
4. Measurement entry → Enable → Start are separate user actions; no automatic restart after reconnect.
5. Stop has priority over normal commands and cancels profiles/pending thrust. Mock uses zero → bounded Feedback wait → disable → mode stop. Hardware uses atomic firmware command ID 8, then confirms zero/disabled/stopped/Standby; emergency uses Safe mode command. It is not a hardwired emergency stop.

On loss: show `TMS CONNECTION LOST / THRUST COMMAND DISABLED`, clear command queues, invalidate session, prohibit new thrust. Sending a packet is not evidence that the motor stopped. SAFE display requires TMS feedback.

Hardware connection now uses the explicit upstream USB VCP adapter. Fault/stale STATUS block operation, and reconnect requires user preparation. Coefficient Apply is disabled because firmware has no coefficient echo/ACK. Command state equality is not command correlation. Shutdown/Disconnect currently stop heartbeat without waiting for motor Stop confirmation; use Stop and verify feedback first. Firmware integration tests on real hardware remain pending. Unit tests cannot certify motor safety.
