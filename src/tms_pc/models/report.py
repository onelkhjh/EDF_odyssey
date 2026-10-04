from dataclasses import dataclass

FourChannels = tuple[float, float, float, float]


@dataclass(frozen=True)
class HardwareReport:
    """Firmware report_t values, preserving names and unconfirmed units."""
    packet_counter: int
    ref_time: float
    thrust: float
    deg: FourChannels
    voltage_edf: float
    current_edf: float
    deg_m: FourChannels
    logic_voltage: float
    battery_percent: float
    subsystem_status: int
    padding: bytes
