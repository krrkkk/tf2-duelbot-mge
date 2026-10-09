import logging
import logging.handlers
import os
import sys


sys.dont_write_bytecode = True

os.environ.pop("QT_PLUGIN_PATH", None)
os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)

from mgebot_launcher.storage import data_directory

folder = data_directory()
folder.mkdir(parents=True, exist_ok=True)
handler = logging.handlers.RotatingFileHandler(folder / "application.log", maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
logging.basicConfig(handlers=[handler], level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def exception_hook(kind, value, traceback):
    logging.error("Unhandled application error", exc_info=(kind, value, traceback))
    if sys.__stderr__ is not None:
        sys.__excepthook__(kind, value, traceback)


sys.excepthook = exception_hook

if __name__ == "__main__":
    try:
        from mgebot_launcher.__main__ import main
        raise SystemExit(main())
    except Exception:
        logging.exception("Application startup failed")
        raise
