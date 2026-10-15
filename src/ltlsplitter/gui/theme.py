from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QPushButton, QSizePolicy

BACKGROUND = "#f4f5f7"
SURFACE = "#ffffff"
BORDER = "#d9dde3"
TEXT = "#1f2933"
TEXT_MUTED = "#52606d"
ACCENT = "#2f6fed"
ACCENT_HOVER = "#255ed1"
ACCENT_SOFT = "#e8efff"
DISABLED_TEXT = "#a0a7b2"
DISABLED_BG = "#eceef1"

# A flat, light theme applied app-wide (see apply_theme) -- the only styling this project had
# before was a handful of inline setStyleSheet() calls for semantic pass/fail colors (still
# respected: a widget's own setStyleSheet always wins over these broader selectors). Qt's
# built-in widget styles vary a lot by platform/desktop environment and often don't fully honor
# a stylesheet unless the base style is "Fusion" first -- see apply_theme.
STYLESHEET = f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT};
    font-size: 13px;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QLabel {{
    background: transparent;
}}

QToolTip {{
    background-color: {TEXT};
    color: {SURFACE};
    border: none;
    padding: 4px 6px;
    border-radius: 4px;
}}

QPushButton {{
    background-color: {SURFACE};
    color: {ACCENT};
    border: 1px solid {ACCENT};
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {ACCENT_SOFT};
}}
QPushButton:pressed {{
    background-color: {ACCENT_HOVER};
    color: {SURFACE};
}}
QPushButton:disabled {{
    color: {DISABLED_TEXT};
    border-color: {DISABLED_TEXT};
    background-color: {DISABLED_BG};
}}

/* The wizard's main forward-progress action -- see MainWindow.next_button -- is the one button
   on every page guaranteed to matter, so it gets the single filled/accent treatment instead of
   the outlined default every other button uses. */
QPushButton#primaryButton {{
    background-color: {ACCENT};
    color: {SURFACE};
    border: 1px solid {ACCENT};
}}
QPushButton#primaryButton:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#primaryButton:disabled {{
    background-color: {DISABLED_BG};
    color: {DISABLED_TEXT};
    border-color: {DISABLED_TEXT};
}}

QLineEdit, QListWidget, QTreeWidget {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {ACCENT};
    selection-color: {SURFACE};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}

QTreeWidget::item, QListWidget::item {{
    padding: 4px 2px;
    border-radius: 4px;
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background-color: {ACCENT_SOFT};
    color: {TEXT};
}}

QHeaderView::section {{
    background-color: {BACKGROUND};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 4px;
    font-weight: 600;
}}

QTreeView::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background-color: {SURFACE};
}}
QTreeView::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QMenu {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
}}
QMenu::item {{
    padding: 4px 16px;
}}
QMenu::item:selected {{
    background-color: {ACCENT_SOFT};
}}
"""


def compact(button: QPushButton) -> QPushButton:
    """A QPushButton added directly to a QVBoxLayout, with no sibling claiming the leftover
    space, stretches to fill the full row -- QPushButton's default horizontal size policy
    (Minimum) treats its sizeHint as a floor, not a fixed width. Every standalone action button
    across the wizard pages wants its natural, content-sized width instead."""
    button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return button


def _build_app_icon() -> QIcon:
    """Draws a small icon in-process (a branch splitting one node into two, the app's core
    operation) rather than shipping a separate image asset -- avoids a packaging/data-file
    dependency for something this simple."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor(ACCENT))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 14, 14)

    pen = painter.pen()
    pen.setColor(QColor(SURFACE))
    pen.setWidth(4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(18, 32, 34, 20)
    painter.drawLine(18, 32, 34, 44)

    painter.setBrush(QColor(SURFACE))
    painter.setPen(Qt.PenStyle.NoPen)
    for cx, cy in ((18, 32), (34, 20), (34, 44)):
        painter.drawEllipse(cx - 5, cy - 5, 10, 10)

    painter.end()
    return QIcon(pixmap)


def apply_theme(app: QApplication) -> QIcon:
    """Sets a consistent flat/light look app-wide. Returns the generated app icon so callers
    can also set it on their top-level window (QIcon doesn't automatically apply to windows
    created before/without it)."""
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    icon = _build_app_icon()
    app.setWindowIcon(icon)
    return icon
