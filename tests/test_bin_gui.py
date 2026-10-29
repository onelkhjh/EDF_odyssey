import csv
import struct
import time

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from tms_pc.controller import TMSController
from tms_pc.gui.main_window import MainWindow


def test_bin_extraction_from_gui(app, tmp_path, monkeypatch):
    payload = bytearray(144)
    # SD counter/padding precede the PC report. Measurement mode, valid loadcell.
    struct.pack_into("<4B", payload, 8, 4, 0, 0, 0)
    struct.pack_into("<2B", payload, 50, 1, 1)
    struct.pack_into("<f", payload, 140, 12345.5)
    body = b"AB\x00\x00" + payload
    frame = body + struct.pack("<I", sum(body))
    source = tmp_path / "DATA0001.BIN"
    source.write_bytes(frame + bytes(512 - len(frame)) + bytes(512))
    target = tmp_path / "parsed.csv"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(source), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(target), ""))
    c = TMSController()
    window = MainWindow(c)
    try:
        window.parse_bin()
        assert window.analysis_busy
        assert not window.parse_bin_button.isEnabled()
        deadline = time.monotonic() + 5
        while window.analysis_busy and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(10)
        assert not window.analysis_busy
        assert "Extracted 1 records" in window.bin_status.text()
        with target.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 1
        assert float(rows[0]["rpm"]) == 12345.5
        # Selecting an existing destination must preserve its contents.
        original = target.read_bytes()
        errors = []
        monkeypatch.setattr(window, "show_error", errors.append)
        window.parse_bin()
        assert errors and "already exists" in errors[0]
        assert target.read_bytes() == original
    finally:
        window.analysis_manager.pool.waitForDone(5000)
        window.close()
        c.timer.stop()
        app.processEvents()


def test_bin_dialog_cancel_does_not_start_job(app, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: ("", ""))
    c = TMSController()
    window = MainWindow(c)
    try:
        window.parse_bin()
        assert not window.analysis_busy
        assert not window.analysis_manager.jobs
    finally:
        window.close()
        c.timer.stop()
        app.processEvents()
