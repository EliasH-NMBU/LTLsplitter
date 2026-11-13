from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCursor, QGuiApplication


class _CallThread(QThread):
    """Runs one blocking call off the GUI thread. The thread object itself lives on the GUI
    thread, so `finished_with` is delivered back there (queued) and handlers may touch widgets."""

    finished_with = Signal(object, object)  # (result, exception-or-None)

    def __init__(self, fn: Callable[[], Any], parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
        except BaseException as exc:  # noqa: BLE001 -- handed back to the GUI thread to report
            self.finished_with.emit(None, exc)
        else:
            self.finished_with.emit(result, None)


def run_in_background(
    parent,
    fn: Callable[[], Any],
    on_done: Callable[[Any, BaseException | None], None],
    busy_widgets=(),
) -> _CallThread:
    """Runs `fn()` in a worker thread so slow work (LLM/network calls) doesn't freeze the
    window -- which is what makes the desktop show "<app> is not responding".

    While it runs, `busy_widgets` are disabled and a busy cursor is shown; then
    `on_done(result, exc)` is called on the GUI thread."""
    widgets = [w for w in busy_widgets if w is not None]
    for w in widgets:
        w.setEnabled(False)
    QGuiApplication.setOverrideCursor(QCursor(Qt.CursorShape.BusyCursor))

    thread = _CallThread(fn, parent)

    def _finish(result, exc) -> None:
        QGuiApplication.restoreOverrideCursor()
        for w in widgets:
            w.setEnabled(True)
        try:
            on_done(result, exc)
        finally:
            thread.deleteLater()

    thread.finished_with.connect(_finish)
    thread.start()
    return thread
