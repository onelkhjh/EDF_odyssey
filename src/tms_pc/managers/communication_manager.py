from dataclasses import dataclass
import itertools
import logging
import queue
import threading
import time
from PySide6.QtCore import QObject, Signal
from tms_pc.communication.packet import MockCodec, Packet
from tms_pc.communication.transport import Transport
from tms_pc.config.settings import Settings
from tms_pc.models.enums import PacketType

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Outgoing:
    token: int
    packet: Packet
    generation: int


class CommunicationManager(QObject):
    packet_received = Signal(int, object)
    sent = Signal(int, int, float)
    connection = Signal(int, bool, str)
    warning = Signal(int, str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.queue: queue.PriorityQueue = queue.PriorityQueue()
        self.counter = itertools.count()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.transport: Transport | None = None
        self.codec = MockCodec(settings.max_payload)
        self.lock = threading.Lock()
        self.generation = 0
        self.session = 0

    def connect_transport(self, transport: Transport) -> None:
        if self.thread and self.thread.is_alive():
            raise ValueError("Disconnect first")
        self.clear_queue()
        self.codec = MockCodec(self.settings.max_payload)
        self.transport = transport
        self.stop_event.clear()
        self.session += 1
        self.thread = threading.Thread(target=self._run, args=(self.session,), name="TMS-IO", daemon=True)
        self.thread.start()

    def submit(self, packet: Packet, priority: int = 10) -> int:
        with self.lock:
            token = next(self.counter)
            self.queue.put((priority, token, Outgoing(token, packet, self.generation)))
        log.info("Command %s %s", packet.kind.name, packet.value)
        return token

    def clear_queue(self) -> None:
        with self.lock:
            self.generation += 1
            while True:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break

    def disconnect(self) -> None:
        self.stop_event.set()
        self.clear_queue()

    def _run(self, session: int) -> None:
        transport = self.transport
        assert transport is not None
        try:
            transport.connect()
            self.connection.emit(session, True, "CONNECTED — awaiting STATUS")
            last_rx = time.monotonic()
            while not self.stop_event.is_set():
                try:
                    _, _, outgoing = self.queue.get_nowait()
                except queue.Empty:
                    outgoing = None
                if outgoing is not None:
                    with self.lock:
                        if not self.stop_event.is_set() and outgoing.generation == self.generation:
                            transport.send(self.codec.encode(outgoing.packet))
                            self.sent.emit(session, outgoing.token, time.monotonic())
                data = transport.read()
                for packet in self.codec.feed(data):
                    if packet.kind in (PacketType.STATUS, PacketType.TELEMETRY, PacketType.FAULT):
                        last_rx = time.monotonic()
                        self.packet_received.emit(session, packet)
                for error in self.codec.errors:
                    self.warning.emit(session, "Packet rejected: " + error)
                if time.monotonic() - last_rx > self.settings.connection_timeout_s:
                    raise ConnectionError("TMS CONNECTION LOST / THRUST COMMAND DISABLED")
                self.stop_event.wait(self.settings.worker_period_s)
        except Exception as exc:
            log.exception("Communication error")
            self.connection.emit(session, False, str(exc))
        finally:
            self.clear_queue()
            try:
                transport.disconnect()
            except Exception:
                log.exception("Disconnect error")
            self.connection.emit(session, False, "DISCONNECTED")
