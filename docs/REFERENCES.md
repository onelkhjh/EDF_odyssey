# Implementation References

Reviewed 2026-10-03. Official library documentation guides the PC implementation; it does not define the TMS firmware protocol.

Similar thrust experiment repositories and actual Python analysis/acquisition code are reviewed separately in [EXPERIMENT_CODE_REFERENCES.md](EXPERIMENT_CODE_REFERENCES.md), including local gaps, implementation priorities and defects that should not be inherited.

| Reference | Finding | Application |
|---|---|---|
| [pySerial API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html) | Timed read may return fewer bytes than requested; write is blocking unless write_timeout is set; serial_for_url supports port/URL backends | Configurable bounded read/write timeouts, bounded read size, loopback transport tests; decoder consumes a stream, never one read=one packet |
| [pySerial loopback](https://pyserial.readthedocs.io/en/latest/url_handlers.html#loop) | loop:// simulates TX/RX for application tests | Exercise real pySerial API and fragmented/concatenated Mock packets without a COM device |
| [Qt Signals and Slots](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/signals_and_slots.html) | QObject receiver thread affinity and queued connections govern slot execution | Explicit queued connections to decorated Controller/AnalysisManager slots; job cleanup in owner thread |
| [Qt Threading Basics](https://doc.qt.io/qtforpython-6.8/overviews/qtdoc-thread-basics.html) | GUI objects belong in GUI thread | Keep I/O and analysis in workers; GUI only renders delivered results |
| [pyqtgraph PlotDataItem](https://pyqtgraph.readthedocs.io/en/pyqtgraph-0.13.7/api_reference/graphicsItems/plotdataitem.html) | NumPy arrays, clipping and downsampling can reduce rendering costs | Shared bounded NumPy snapshot per refresh; clipToView/autoDownsample with peak method for time plots; raw data retained for analysis/export |
| [Python struct](https://docs.python.org/3/library/struct.html#byte-order-size-and-alignment) | Explicit < or > gives standard widths and no implicit padding | Existing report_t decoder retains explicit endian and explicit padding bytes; no native @ layout |

## Decisions and limits

- Serial read/write timeouts and chunk caps are PC settings, not firmware timing specifications. Production UART data bits/parity/stop bits, DTR/RTS behavior, flow control, baud and safety timeout must be verified on hardware.
- Loopback proves library integration and streaming behavior only, not USB/COM reliability or TMS compatibility.
- report_t has no synchronization marker or checksum in the supplied structure. Do not infer framing from 64-byte USB reads. Real framing adapter awaits firmware evidence.
- Graph downsampling affects display only. Statistics and energy calculations keep original samples.
- No performance improvement percentage or native desktop visual QA is claimed without measurements.

## Validation

`.venv\Scripts\python.exe -m pytest -q`: 42 passed in 8.41s after applying changes. Added real pySerial loop:// fragmentation/concatenation/closed-port tests, invalid timeout validation, analysis success/error thread-affinity and job cleanup checks, and bounded plotting snapshot checks. GUI Analysis test detected a curve-parent initialization error with clipping enabled before insertion; resolved by inserting an empty curve before setting clipping/downsampling and data. Existing GUI/PNG export and reconnect tests pass with the optimization.
