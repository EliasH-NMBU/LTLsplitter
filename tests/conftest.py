import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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
