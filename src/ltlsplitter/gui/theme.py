from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSizePolicy

StatusKind = Literal["success", "danger", "muted"]


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    border: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    disabled_text: str
    disabled_bg: str
    success: str
    danger: str


LIGHT = Palette(
    background="#f4f5f7", surface="#ffffff", border="#d9dde3", text="#1f2933",
    text_muted="#52606d", accent="#2f6fed", accent_hover="#255ed1", accent_soft="#e8efff",
    disabled_text="#a0a7b2", disabled_bg="#eceef1", success="#1a7f37", danger="#b00020",
)

DARK = Palette(
    background="#1b1e23", surface="#242830", border="#3a3f48", text="#e7eaf0",
    text_muted="#9aa4b2", accent="#5b8dfb", accent_hover="#7ea2fc", accent_soft="#28324a",
    disabled_text="#5b6270", disabled_bg="#2a2e36", success="#3fb950", danger="#f85149",
)


def build_stylesheet(p: Palette) -> str:
    """A flat theme applied app-wide (see ThemeManager.apply) -- Qt's built-in widget styles
    vary a lot by platform/desktop environment and often don't fully honor a stylesheet unless
    the base style is "Fusion" first -- see ThemeManager.apply.

    Includes two kinds of selector that let widgets built once still follow a later theme
    toggle without re-applying their own inline styles: object names for the page chrome
    (QLabel#pageTitle etc. -- see pages/base.py) and a dynamic "status" property for semantic
    pass/fail/neutral labels (see set_status)."""
    return f"""
QWidget {{
    background-color: {p.background};
    color: {p.text};
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
    background-color: {p.text};
    color: {p.surface};
    border: none;
    padding: 4px 6px;
    border-radius: 4px;
}}

QPushButton {{
    background-color: {p.surface};
    color: {p.accent};
    border: 1px solid {p.accent};
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {p.accent_soft};
}}
QPushButton:pressed {{
    background-color: {p.accent_hover};
    color: {p.surface};
}}
QPushButton:disabled {{
    color: {p.disabled_text};
    border-color: {p.disabled_text};
    background-color: {p.disabled_bg};
}}

/* The wizard's main forward-progress action -- see MainWindow.next_button -- is the one button
   on every page guaranteed to matter, so it gets the single filled/accent treatment instead of
   the outlined default every other button uses. */
QPushButton#primaryButton {{
    background-color: {p.accent};
    color: {p.surface};
    border: 1px solid {p.accent};
}}
QPushButton#primaryButton:hover {{
    background-color: {p.accent_hover};
}}
QPushButton#primaryButton:disabled {{
    background-color: {p.disabled_bg};
    color: {p.disabled_text};
    border-color: {p.disabled_text};
}}

QLineEdit, QListWidget, QTreeWidget {{
    background-color: {p.surface};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {p.accent};
    selection-color: {p.surface};
}}
QLineEdit:focus {{
    border: 1px solid {p.accent};
}}

QTreeWidget::item, QListWidget::item {{
    padding: 4px 2px;
    border-radius: 4px;
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background-color: {p.accent_soft};
    color: {p.text};
}}

QHeaderView::section {{
    background-color: {p.background};
    color: {p.text_muted};
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 4px;
    font-weight: 600;
}}

QTreeView::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {p.border};
    border-radius: 3px;
    background-color: {p.surface};
}}
QTreeView::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {p.border};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.accent};
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
    background: {p.border};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QMenu {{
    background-color: {p.surface};
    border: 1px solid {p.border};
}}
QMenu::item {{
    padding: 4px 16px;
}}
QMenu::item:selected {{
    background-color: {p.accent_soft};
}}

QLabel#pageTitle {{
    font-size: 19px;
    font-weight: 700;
    color: {p.accent};
}}
QLabel#pageDescription {{
    color: {p.text_muted};
}}
QFrame#divider {{
    background-color: {p.border};
    border: none;
}}

QLabel[status="success"] {{
    color: {p.success};
}}
QLabel[status="danger"] {{
    color: {p.danger};
}}
QLabel[status="muted"] {{
    color: {p.text_muted};
}}
"""


_SETTINGS_ORG = "LTLsplitter"
_SETTINGS_APP = "LTLsplitter"
_SETTINGS_KEY = "appearance/theme"


class ThemeManager(QObject):
    """Owns the active light/dark mode, persisted across runs via QSettings. `toggle()`
    re-applies the app-wide stylesheet immediately (Qt re-polishes every existing widget when
    QApplication.setStyleSheet is called, so already-built pages pick up the new colors without
    needing to be rebuilt) and emits `changed` for anything that also needs to update itself,
    such as the toggle button's own label."""

    changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        saved = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETTINGS_KEY, "light")
        self.mode: Literal["light", "dark"] = "dark" if saved == "dark" else "light"

    @property
    def palette(self) -> Palette:
        return DARK if self.mode == "dark" else LIGHT

    def apply(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(self.palette))

    def toggle(self) -> None:
        self.mode = "light" if self.mode == "dark" else "dark"
        QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(_SETTINGS_KEY, self.mode)
        self.apply()
        self.changed.emit(self.mode)


theme_manager = ThemeManager()


def set_status(label: QLabel, status: StatusKind | None) -> None:
    """Marks a label with a semantic status ("success"/"danger"/"muted", or None to clear) via
    a dynamic Qt property rather than an inline hex color, so the actual color comes from the
    active theme's stylesheet (see the QLabel[status=...] rules in build_stylesheet) and follows
    any later theme toggle automatically."""
    label.setProperty("status", status)
    label.style().unpolish(label)
    label.style().polish(label)


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
    dependency for something this simple. Always drawn with the light palette's colors: it's a
    fixed brand mark (shown in the taskbar/title bar), not page content, so it doesn't need to
    follow the active theme."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor(LIGHT.accent))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 14, 14)

    pen = painter.pen()
    pen.setColor(QColor(LIGHT.surface))
    pen.setWidth(4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(18, 32, 34, 20)
    painter.drawLine(18, 32, 34, 44)

    painter.setBrush(QColor(LIGHT.surface))
    painter.setPen(Qt.PenStyle.NoPen)
    for cx, cy in ((18, 32), (34, 20), (34, 44)):
        painter.drawEllipse(cx - 5, cy - 5, 10, 10)

    painter.end()
    return QIcon(pixmap)


def apply_theme(app: QApplication) -> QIcon:
    """Sets a consistent flat look app-wide, in whichever mode (light/dark) was last saved.
    Returns the generated app icon so callers can also set it on their top-level window (QIcon
    doesn't automatically apply to windows created before/without it)."""
    app.setStyle("Fusion")
    theme_manager.apply()
    icon = _build_app_icon()
    app.setWindowIcon(icon)
    return icon
