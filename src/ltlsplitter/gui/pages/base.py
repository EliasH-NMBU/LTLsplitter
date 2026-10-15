from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.theme import ACCENT, BORDER, TEXT_MUTED


class WizardPage(QWidget):
    title: str = ""
    description: str = ""

    def __init__(self, state: ProjectState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state

        # A page's content (in particular, a long tool-error message in a result QLabel, e.g.
        # Strix or Kind2's raw output on realizability_check.py) can need more vertical space
        # than the window has -- without a scroll area, that content is just silently clipped,
        # with no way to read the rest of it. Every page's content goes through
        # `self.content_layout`, inside this scroll area, so this fix covers all of them.
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        outer_layout.addWidget(scroll_area)

        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(20, 18, 20, 18)
        self.content_layout.setSpacing(10)
        scroll_area.setWidget(content_widget)

        title_label = QLabel(self.title)
        title_label.setStyleSheet(f"font-size: 19px; font-weight: 700; color: {ACCENT};")
        self.content_layout.addWidget(title_label)

        description_label = QLabel(self.description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(f"color: {TEXT_MUTED};")
        self.content_layout.addWidget(description_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {BORDER}; border: none;")
        self.content_layout.addWidget(divider)
        self.content_layout.addSpacing(4)

    def on_show(self) -> None:
        """Called by MainWindow whenever this page becomes the current page,
        so it can refresh content that depends on other pages' state."""
