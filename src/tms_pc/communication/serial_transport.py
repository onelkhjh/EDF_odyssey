import serial
import math
from serial.tools import list_ports
from tms_pc.config.settings import Settings


def available_ports() -> list[str]:
    return [port.device for port in list_ports.comports()]


class SerialTransport:
    def __init__(self, port: str, baud: int, settings: Settings = Settings()) -> None:
        if not port.strip() or isinstance(baud, bool) or not isinstance(baud, int) or baud <= 0:
            raise ValueError("Serial requires a port and explicit positive integer baud")
        if any(not math.isfinite(value) or value <= 0 for value in (settings.serial_read_timeout_s, settings.serial_write_timeout_s)):
            raise ValueError("Serial read/write timeouts must be finite and positive")
        if not isinstance(settings.serial_max_read_bytes, int) or settings.serial_max_read_bytes < 1:
            raise ValueError("Serial read chunk limit must be a positive integer")
        self.port, self.baud = port, baud
        self.settings = settings
        self.device: serial.Serial | None = None

    def connect(self) -> None:
        if self.device is not None:
            raise ConnectionError("Serial already connected; disconnect first")
        self.device = serial.serial_for_url(self.port, baudrate=self.baud,
                                            timeout=self.settings.serial_read_timeout_s,
                                            write_timeout=self.settings.serial_write_timeout_s)

    def disconnect(self) -> None:
        if self.device:
            self.device.close()
            self.device = None

    def send(self, data: bytes) -> None:
        if not self.device:
            raise ConnectionError("Serial not connected")
        if self.device.write(data) != len(data):
            raise IOError("Partial serial write")

    def read(self) -> bytes:
        if not self.device:
            raise ConnectionError("Serial not connected")
        return self.device.read(max(1, min(self.device.in_waiting, self.settings.serial_max_read_bytes)))
