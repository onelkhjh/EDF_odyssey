# State Machine

Hardware profile (upstream bd60824): Safe=0, Boot=1, Standby=2, Calibration=3, Measurement=4; Mock enum values remain separate. Hardware Stop/Disable/Run=false ends Measurement by entering Standby directly, so no persistent FINISHED state is expected. Start requires a thruster report <=500ms old. Calibration Acquire requires Run=true; the controller requests Run and waits for STATUS before Acquire. Hardware coefficient Apply is disabled pending verifiable feedback. See PROTOCOL.md for current wire definitions; the sequence below describes Mock behavior unless specified otherwise.

Mode: BOOT, SAFE, STANDBY, CALIBRATION, MEASUREMENT. BOOT is observed only. PC can request SAFE at any time; normal transitions require mode_run=false and thrust disabled. Running mode changes are refused except SAFE.

Measurement: enter → IDLE → enable feedback → READY → start feedback → RUNNING → stop sequence → FINISHED → STANDBY. New session requires re-entry or explicit disable/enable preparation after stopping. Reconnection always invalidates previous session.

Guard rules:
- disconnected/stale: all operational requests refused.
- STANDBY: no enable/start/thrust; sensor display only.
- CALIBRATION: acquisition only, no thrust; factor apply only while not acquiring.
- MEASUREMENT IDLE: enable allowed, start refused.
- READY: start allowed only after enable Feedback.
- RUNNING: thrust allowed only if mode_run and enable Feedback are true.
- Stop: cancel profile and queued thrust; request 0%, bounded Feedback wait, disable, stop. FINISHED only on matching final Feedback.
- Failed Feedback never creates successful observed state. Connection loss requires reconnect and user preparation.

Runtime is TMS owned. Profile starts at first running telemetry runtime, advances on received runtime, and stops on regression/discontinuity warning rather than using PC wall-clock for motion.

Disable from READY returns to IDLE; completed RUNNING sessions retain FINISHED until a new mode entry via STANDBY. Late packets received after disconnect cannot restore connected state. Missing command Feedback triggers an ordered emergency Stop request with bounded per-step waits, without treating the stop as confirmed until STATUS matches.
