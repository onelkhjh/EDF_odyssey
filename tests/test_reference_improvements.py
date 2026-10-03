from dataclasses import replace
import threading
import time
import numpy as np
import pytest
from PySide6.QtCore import QObject, Slot
from PySide6.QtTest import QTest
from tms_pc.config.settings import Settings
from tms_pc.communication.serial_transport import SerialTransport
from tms_pc.communication.packet import MockCodec, Packet
from tms_pc.models.enums import PacketType, Mode
from tms_pc.models.status import Status
from tms_pc.models.telemetry import Telemetry
from tms_pc.managers.analysis_manager import AnalysisManager
from tms_pc.managers.visualization_manager import VisualizationManager


def test_serial_loopback_fragmented_and_concatenated_packets():
    settings = Settings(serial_read_timeout_s=.01, serial_max_read_bytes=7)
    transport = SerialTransport("loop://", 115200, settings)
    transport.connect()
    try:
        with pytest.raises(ConnectionError):
            transport.connect()
        expected = [Packet(PacketType.STATUS, Status(mode=Mode.STANDBY)),
                    Packet(PacketType.TELEMETRY, Telemetry(1., 24., 2., 3., 101., 3100.))]
        encoder = MockCodec()
        wire = b"".join(encoder.encode(packet) for packet in expected)
        transport.send(wire[:3])
        decoder = MockCodec()
        assert decoder.feed(transport.read()) == []
        transport.send(wire[3:])
        packets = []
        deadline = time.monotonic() + 2
        while len(packets) < len(expected) and time.monotonic() < deadline:
            chunk = transport.read()
            assert len(chunk) <= settings.serial_max_read_bytes
            packets.extend(decoder.feed(chunk))
        assert packets == expected
        assert transport.read() == b""
    finally:
        transport.disconnect()
    with pytest.raises(ConnectionError):
        transport.send(b"x")
    with pytest.raises(ConnectionError):
        transport.read()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_serial_rejects_unbounded_or_invalid_timeouts(timeout):
    with pytest.raises(ValueError):
        SerialTransport("loop://", 115200, replace(Settings(), serial_read_timeout_s=timeout))
    with pytest.raises(ValueError):
        SerialTransport("loop://", 115200, replace(Settings(), serial_write_timeout_s=timeout))


class Receiver(QObject):
    def __init__(self):
        super().__init__()
        self.received = []

    @Slot(object)
    def done(self, value):
        self.received.append((value, threading.get_ident()))

    @Slot(str)
    def failed(self, value):
        self.received.append((value, threading.get_ident()))


@pytest.mark.parametrize("fail", [False, True])
def test_analysis_result_and_cleanup_run_in_owner_thread(app, fail):
    owner_thread = threading.get_ident()
    manager = AnalysisManager()
    receiver = Receiver()
    manager.completed.connect(receiver.done)
    manager.failed.connect(receiver.failed)

    def task():
        assert threading.get_ident() != owner_thread
        if fail:
            raise ValueError("Expected worker error")
        return "worker result"

    manager.submit(task)
    deadline = time.monotonic() + 2
    while not receiver.received and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    assert receiver.received == [("Expected worker error" if fail else "worker result", owner_thread)]
    assert manager.jobs == []
    manager.pool.waitForDone(1000)


def test_plot_snapshot_is_bounded_and_retains_original_values():
    manager = VisualizationManager(2)
    for i in range(3):
        manager.append(Telemetry(float(i), 24. + i, 1., 2., 101., 2100.), i * 10.)
    times, values = manager.snapshot(("motor_voltage", "thrust_command"))
    np.testing.assert_array_equal(times, [1., 2.])
    np.testing.assert_array_equal(values["motor_voltage"], [25., 26.])
    np.testing.assert_array_equal(values["thrust_command"], [10., 20.])
    values["motor_voltage"][0] = 0
    assert manager.samples[0][0].motor_voltage == 25
