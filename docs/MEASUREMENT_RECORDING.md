# Measurement recording

Start requests in Measurement automatically create a separate directory under
`recordings/`, with the timestamp and `_hardware` or `_mock` suffix.

`measurement.csv` is flushed after every received telemetry sample. It includes
elapsed PC time since the Start request, firmware runtime, the PC requested
throttle (%), TMS reported applied throttle (%), measured load-cell thrust (N),
voltage, current, pressure, raw load-cell value, operating state, and fault.
Elapsed PC time remains increasing even if firmware runtime resets.

`thrust_time.svg` is generated after confirmed end of operation or disconnection.
Open it in a browser to see separate command (%) and measured thrust (N) panels.
The Measurement page displays the recording directory. Recording is independent
of the bounded live graph buffer and remains on disk after reconnecting.

An unsuccessful Start attempt also produces a recording. Inspect `mode_run` and
`fault` to distinguish an actual run from a rejected attempt. Only received
samples are saved; missing data during communication loss is not reconstructed.
On abrupt process termination the flushed CSV remains available, but the SVG
may not have been generated.
