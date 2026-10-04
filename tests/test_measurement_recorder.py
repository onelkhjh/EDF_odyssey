import csv
import xml.etree.ElementTree as ET

from tms_pc.managers.measurement_recorder import MeasurementRecorder
from tms_pc.models.enums import Mode
from tms_pc.models.status import Status
from tms_pc.models.telemetry import Telemetry


def test_recording_flushes_and_preserves_requested_applied_and_fault(tmp_path):
    recorder = MeasurementRecorder(tmp_path)
    recorder.begin(hardware=True)
    recorder.append(Telemetry(12, 24, 2, 3, 101, 3000), Status(mode=Mode.MEASUREMENT, mode_run=True, thrust_enable=True, thrust_command=20), 30, "")
    # The first sample must already be readable before Stop or Disconnect.
    with recorder.path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["pc_requested_percent"] == "30"
    assert rows[0]["thrust_command"] == "20"
    recorder.append(Telemetry(13, 24, 0, float("nan"), 101, 0), Status(mode=Mode.SAFE), 30, "SD")
    recorder.finish()
    with recorder.path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[-1]["fault"] == "SD"
    assert float(rows[-1]["elapsed_s"]) >= float(rows[0]["elapsed_s"])
    graph = ET.parse(recorder.path.with_name("thrust_time.svg"))
    assert len(graph.findall(".//{http://www.w3.org/2000/svg}polyline")) == 3
    old_path = recorder.path
    recorder.begin(hardware=False)
    recorder.finish()
    assert old_path.exists() and recorder.path != old_path
