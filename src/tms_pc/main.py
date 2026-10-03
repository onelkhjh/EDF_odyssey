import argparse
import logging
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from tms_pc.controller import TMSController
from tms_pc.gui.main_window import MainWindow
from tms_pc.utils.logger import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="TMS-PC ground control")
    parser.add_argument("--mock", action="store_true", help="Auto-connect simulator")
    parser.add_argument("--smoke-seconds", type=float, help="Close automatically after GUI smoke test")
    args = parser.parse_args()
    configure_logging()
    logging.info("Application Start")
    app = QApplication(sys.argv[:1])
    controller = TMSController()
    window = MainWindow(controller, args.mock)
    window.show()
    if args.smoke_seconds:
        QTimer.singleShot(int(args.smoke_seconds * 1000), window.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
