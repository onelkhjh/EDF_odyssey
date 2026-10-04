from enum import Enum, auto


class Mode(Enum):
    BOOT = auto()
    SAFE = auto()
    STANDBY = auto()
    CALIBRATION = auto()
    MEASUREMENT = auto()


class MeasurementState(Enum):
    IDLE = auto()
    READY = auto()
    RUNNING = auto()
    FINISHED = auto()


class PacketType(Enum):
    COMMAND_MODE = auto()
    COMMAND_MODE_RUN = auto()
    COMMAND_CALIBRATION_ACQUIRE = auto()
    COMMAND_THRUST_ENABLE = auto()
    COMMAND_THRUST = auto()
    COMMAND_CALIBRATION_FACTOR = auto()
    STATUS = auto()
    TELEMETRY = auto()
    FAULT = auto()
    HARDWARE_REPORT = auto()
    HEARTBEAT = auto()
    STOP = auto()
