from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.decomposition_validation import DecompositionValidationPage
from ltlsplitter.gui.pages.import_split import ImportSplitPage
from ltlsplitter.gui.pages.monitor_export import MonitorExportPage
from ltlsplitter.gui.pages.realizability_check import RealizabilityCheckPage

PAGE_CLASSES = [
    ImportSplitPage,
    DecompositionValidationPage,
    RealizabilityCheckPage,
    MonitorExportPage,
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LTLsplitter")
        self.resize(900, 600)

        self.state = ProjectState()

        self.stack = QStackedWidget()
        for page_class in PAGE_CLASSES:
            self.stack.addWidget(page_class(self.state))
        self.stack.currentChanged.connect(self._on_page_changed)

        self.back_button = QPushButton("Back")
        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("primaryButton")  # the one button on every page that
        # always matters -- see theme.py's QPushButton#primaryButton rule -- gets the filled
        # accent treatment, everything else stays outlined.
        for button in (self.back_button, self.next_button):
            button.setMinimumWidth(96)
        self.back_button.clicked.connect(self.go_back)
        self.next_button.clicked.connect(self.go_next)

        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(20, 10, 20, 14)
        nav_layout.addWidget(self.back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_button)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.stack)
        central_layout.addLayout(nav_layout)
        self.setCentralWidget(central)

        self._update_nav_buttons()
        self.stack.widget(self.stack.currentIndex()).on_show()

    def go_back(self) -> None:
        self.stack.setCurrentIndex(self.stack.currentIndex() - 1)
        self._update_nav_buttons()

    def go_next(self) -> None:
        self.stack.setCurrentIndex(self.stack.currentIndex() + 1)
        self._update_nav_buttons()

    def _on_page_changed(self, index: int) -> None:
        self.stack.widget(index).on_show()

    def _update_nav_buttons(self) -> None:
        index = self.stack.currentIndex()
        self.back_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < self.stack.count() - 1)
