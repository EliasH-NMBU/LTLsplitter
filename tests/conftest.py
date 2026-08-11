import os

import pytest
from PySide6.QtCore import QSettings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolate_qsettings(tmp_path, monkeypatch):
    """Redirect QSettings("LTLsplitter", "LTLsplitter") to a per-test temp directory so
    tests never read or write the real user config file, and don't leak an API key.
    QSettings(org, app) defaults to NativeFormat (not IniFormat), so both must be
    redirected -- setPath is keyed by the exact Format enum value."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path))


def _tool_available(env_var: str, name: str) -> bool:
    from ltlsplitter.core.realizability import ToolNotFoundError, _find_binary

    try:
        _find_binary(env_var, name)
        return True
    except ToolNotFoundError:
        return False


requires_nuxmv = pytest.mark.skipif(
    not _tool_available("NUXMV_PATH", "nuXmv"), reason="nuXmv not installed"
)
requires_strix = pytest.mark.skipif(
    not _tool_available("STRIX_PATH", "strix"), reason="strix not installed"
)


def _ogma_available() -> bool:
    from ltlsplitter.core.ogma import ToolNotFoundError, _find_ogma

    try:
        _find_ogma()
        return True
    except ToolNotFoundError:
        return False


requires_ogma = pytest.mark.skipif(not _ogma_available(), reason="ogma not installed")
