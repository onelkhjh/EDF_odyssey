import math
from tms_pc.models.enums import Mode, MeasurementState, PacketType
from tms_pc.models.status import Status


class StateManager:
    def __init__(self) -> None:
        self.status = Status()
        self.connected = False
        self.measurement = MeasurementState.IDLE

    def observe(self, status: Status) -> None:
        previous = self.status
        self.status = status
        if status.mode != Mode.MEASUREMENT:
            self.measurement = MeasurementState.IDLE
        elif status.mode_run and status.thrust_enable:
            self.measurement = MeasurementState.RUNNING
        elif previous.mode_run:
            self.measurement = MeasurementState.FINISHED
        elif status.thrust_enable:
            self.measurement = MeasurementState.READY
        elif previous.mode != Mode.MEASUREMENT:
            self.measurement = MeasurementState.IDLE
        elif not status.thrust_enable and self.measurement != MeasurementState.FINISHED:
            self.measurement = MeasurementState.IDLE

    def guard(self, kind: PacketType, value: object) -> None:
        if not self.connected:
            raise ValueError("TMS CONNECTION LOST / THRUST COMMAND DISABLED")
        s = self.status
        if kind == PacketType.COMMAND_MODE:
            if not isinstance(value, Mode) or value == Mode.BOOT:
                raise ValueError("BOOT cannot be requested")
            if value != Mode.SAFE and (s.mode_run or s.thrust_enable or s.acquire):
                raise ValueError("Stop and disable before changing mode")
        elif kind == PacketType.COMMAND_THRUST_ENABLE:
            if bool(value) and (s.mode != Mode.MEASUREMENT or s.mode_run or self.measurement == MeasurementState.FINISHED):
                raise ValueError("Enter a new Measurement session before Enable")
        elif kind == PacketType.COMMAND_MODE_RUN:
            if bool(value) and (s.mode != Mode.MEASUREMENT or not s.thrust_enable or self.measurement != MeasurementState.READY):
                raise ValueError("Start requires Measurement READY and enable feedback")
        elif kind == PacketType.COMMAND_THRUST:
            number = float(value)
            if not math.isfinite(number) or not 0 <= number <= 100:
                raise ValueError("Thrust must be finite and 0–100%")
            if s.mode != Mode.MEASUREMENT or (number > 0 and not (s.mode_run and s.thrust_enable)):
                raise ValueError("Thrust requires Measurement RUNNING and enabled feedback")
        elif kind == PacketType.COMMAND_CALIBRATION_ACQUIRE:
            if s.mode != Mode.CALIBRATION:
                raise ValueError("Acquire requires Calibration mode")
        elif kind == PacketType.COMMAND_CALIBRATION_FACTOR:
            if s.mode != Mode.CALIBRATION or s.acquire:
                raise ValueError("Apply requires Calibration mode with acquisition stopped")
            slope, offset = value
            if not math.isfinite(slope) or not math.isfinite(offset) or abs(slope) < 1e-12:
                raise ValueError("Invalid calibration factors")
