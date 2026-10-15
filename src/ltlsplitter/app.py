from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ltlsplitter.gui.main_window import MainWindow
from ltlsplitter.gui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    icon = apply_theme(app)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
