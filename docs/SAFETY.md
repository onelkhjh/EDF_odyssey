# Safety

1. PC is not an actual safety system. OS, USB, scheduling and application failures are possible.
2. TMS Firmware independently handles communication timeout: thrust 0, disable, motor stop, SAFE or STANDBY. Firmware timeout and fault policy TBD and must be verified on hardware.
3. PC guard prevents unsafe-state commands. Only STATUS feedback authorizes subsequent steps. BOOT is never requested.
4. Measurement entry → Enable → Start are separate user actions; no automatic restart after reconnect.
5. Stop has priority over normal commands. It cancels profiles and pending thrust and performs zero → bounded Feedback wait → disable → mode stop. No infinite wait. Emergency Stop Request requests the same ordered sequence plus SAFE; it is not a hardwired emergency stop.

On loss: show `TMS CONNECTION LOST / THRUST COMMAND DISABLED`, clear command queues, invalidate session, prohibit new thrust. Sending a packet is not evidence that the motor stopped. SAFE display requires TMS feedback.

Mock enforces independent timeout and rejects illegal transitions; its physics are test fixtures only. Real hardware use is blocked until an explicit reviewed protocol adapter and Firmware safety integration tests exist. Unit tests cannot certify motor safety.
