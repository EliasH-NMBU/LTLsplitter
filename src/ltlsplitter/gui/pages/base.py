from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class WizardPage(QWidget):
    title: str = ""
    description: str = ""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title_label = QLabel(self.title)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        description_label = QLabel(self.description)
        description_label.setWordWrap(True)
        layout.addWidget(description_label)

        layout.addStretch()
