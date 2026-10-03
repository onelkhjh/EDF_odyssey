import zlib
from typing import Protocol


class Checksum(Protocol):
    def calculate(self, data: bytes) -> int: ...


class MockCRC32:
    """Deterministic simulator checksum; replace for confirmed hardware profile."""
    def calculate(self, data: bytes) -> int:
        return zlib.crc32(data) & 0xffffffff
