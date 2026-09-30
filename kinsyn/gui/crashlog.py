"""Crash diagnostics.

A native crash (e.g. a double free inside Qt) leaves a core dump with no
Python context. To make crashes diagnosable this module:

- enables faulthandler, which writes the Python stack of every thread to
  faulthandler.log on SIGSEGV / SIGABRT / SIGBUS / SIGFPE / SIGILL;
- keeps a line-buffered breadcrumb log of recent user actions;
- logs unhandled Python exceptions and Qt warnings to errors.log;
- writes a session marker so the next start can detect an unclean exit.

Logs live in $XDG_STATE_HOME/kinsyn (default ~/.local/state/kinsyn)."""

import faulthandler
import os
import platform
import sys
import time
import traceback
from pathlib import Path

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "kinsyn"
FAULT_LOG = STATE_DIR / "faulthandler.log"
ERROR_LOG = STATE_DIR / "errors.log"
BREADCRUMBS = STATE_DIR / "breadcrumbs.log"
MARKER = STATE_DIR / "session.pid"
MAX_LOG_BYTES = 2_000_000
QT_NOISE = ("propagateSizeHints",)

_fault_file = None
_crumb_file = None


def _stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _rotate(path):
    if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
        path.replace(path.with_suffix(path.suffix + ".old"))


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def previous_crash():
    """If the last session did not exit cleanly, return (pid, started) of it."""
    if not MARKER.exists():
        return None
    try:
        pid, started = MARKER.read_text().split("\n")[:2]
        pid = int(pid)
    except ValueError:
        return None
    if pid == os.getpid() or _pid_alive(pid):
        return None
    return pid, started


def breadcrumb(message):
    """Record a user action. Flushed immediately so it survives a crash."""
    if _crumb_file is not None:
        _crumb_file.write(f"{_stamp()} {message}\n")


def _log_error(text):
    with ERROR_LOG.open("a") as f:
        f.write(f"\n=== {_stamp()} pid {os.getpid()} ===\n{text}\n")


def _excepthook(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    breadcrumb(f"UNHANDLED {exc_type.__name__}: {exc}")
    _log_error(text)
    sys.__stderr__.write(text)
    try:
        from PySide6 import QtWidgets
        if QtWidgets.QApplication.instance() is not None:
            QtWidgets.QMessageBox.warning(
                None, "kinsyn error",
                f"An unexpected error occurred and was logged:\n\n{exc_type.__name__}: {exc}\n\n"
                f"Details: {ERROR_LOG}")
    except Exception:  # never let the error handler itself raise
        pass


def _qt_message_handler(mode, context, message):
    if any(n in message for n in QT_NOISE):
        return
    from PySide6 import QtCore
    level = {QtCore.QtMsgType.QtWarningMsg: "warning", QtCore.QtMsgType.QtCriticalMsg: "critical",
             QtCore.QtMsgType.QtFatalMsg: "fatal"}.get(mode)
    if level:
        _log_error(f"Qt {level}: {message}")
        breadcrumb(f"Qt {level}: {message[:200]}")


def install():
    """Call once at start-up, before creating the QApplication."""
    global _fault_file, _crumb_file
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for p in (FAULT_LOG, ERROR_LOG, BREADCRUMBS):
        _rotate(p)
    crashed = previous_crash()

    from PySide6 import QtCore, __version__ as pyside_version
    header = (f"\n=== session {_stamp()} pid {os.getpid()} | python {platform.python_version()} | "
              f"PySide6 {pyside_version} | Qt {QtCore.qVersion()} | "
              f"{os.environ.get('XDG_SESSION_TYPE', '?')} {os.environ.get('QT_QPA_PLATFORM', '')} ===\n")
    _fault_file = FAULT_LOG.open("a", buffering=1)
    _fault_file.write(header)
    faulthandler.enable(file=_fault_file, all_threads=True)
    _crumb_file = BREADCRUMBS.open("a", buffering=1)
    _crumb_file.write(header)

    MARKER.write_text(f"{os.getpid()}\n{_stamp()}\n")
    sys.excepthook = _excepthook
    QtCore.qInstallMessageHandler(_qt_message_handler)
    return crashed


def clean_exit():
    breadcrumb("clean exit")
    try:
        if MARKER.exists() and MARKER.read_text().split("\n")[0] == str(os.getpid()):
            MARKER.unlink()
    except OSError:
        pass


def tail(path, lines=40):
    try:
        return "".join(path.read_text(errors="replace").splitlines(keepends=True)[-lines:])
    except OSError:
        return ""
