from __future__ import annotations

import argparse
import sys
import hashlib
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from .controller import Controller
from .gui import MainWindow
from .storage import data_directory


def main():
    parser = argparse.ArgumentParser(description="mgebot duel local companion")
    parser.add_argument("--demo", action="store_true", help="Display labelled synthetic data; no game control")
    parser.add_argument("--payload", type=Path, help="Matching local plugin platform archive")
    parser.add_argument("--smoke", action="store_true", help="Open and close the UI for runtime validation; no game operations")
    args = parser.parse_args()
    application = QApplication(sys.argv[:1])
    application.setApplicationName("mgebot duel")
    application.setOrganizationName("avxgroup")
    data = data_directory()
    if args.demo or args.smoke:
        data /= "demo"
    instance = None
    if not args.demo and not args.smoke:
        key = "mgebot-duel-" + hashlib.sha256(str(data.resolve()).encode()).hexdigest()[:16]
        socket = QLocalSocket(); socket.connectToServer(key)
        if socket.waitForConnected(150):
            socket.write(b"activate"); socket.flush(); socket.waitForBytesWritten(150); socket.disconnectFromServer()
            return 0
        QLocalServer.removeServer(key)
        instance = QLocalServer(application)
        instance.listen(key)
    window = MainWindow(data, args.payload, args.demo or args.smoke)
    controller = Controller(window, data, args.demo or args.smoke)
    window.show()
    if instance:
        def activate():
            client = instance.nextPendingConnection()
            if client:
                client.disconnectFromServer(); client.deleteLater()
            if window.isMinimized(): window.showNormal()
            window.raise_(); window.activateWindow()
        instance.newConnection.connect(activate)
    if args.smoke:
        QTimer.singleShot(250, application.quit)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
