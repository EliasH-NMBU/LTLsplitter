from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ltlsplitter.core.project_state import ProjectState


class WizardPage(QWidget):
    title: str = ""
    description: str = ""

    def __init__(self, state: ProjectState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state

        self.content_layout = QVBoxLayout(self)

        title_label = QLabel(self.title)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.content_layout.addWidget(title_label)

        description_label = QLabel(self.description)
        description_label.setWordWrap(True)
        self.content_layout.addWidget(description_label)

    def on_show(self) -> None:
        """Called by MainWindow whenever this page becomes the current page,
        so it can refresh content that depends on other pages' state."""
