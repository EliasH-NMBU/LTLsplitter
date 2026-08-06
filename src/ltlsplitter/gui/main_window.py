from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ltlsplitter.gui.pages.consistency_check import ConsistencyCheckPage
from ltlsplitter.gui.pages.deployment import DeploymentPage
from ltlsplitter.gui.pages.monitor_generation import MonitorGenerationPage
from ltlsplitter.gui.pages.requirement_split import RequirementSplitPage
from ltlsplitter.gui.pages.spec_authoring import SpecAuthoringPage
from ltlsplitter.gui.pages.variable_declaration import VariableDeclarationPage

PAGE_CLASSES = [
    RequirementSplitPage,
    VariableDeclarationPage,
    SpecAuthoringPage,
    ConsistencyCheckPage,
    MonitorGenerationPage,
    DeploymentPage,
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LTLsplitter")
        self.resize(900, 600)

        self.stack = QStackedWidget()
        for page_class in PAGE_CLASSES:
            self.stack.addWidget(page_class())

        self.back_button = QPushButton("Back")
        self.next_button = QPushButton("Next")
        self.back_button.clicked.connect(self.go_back)
        self.next_button.clicked.connect(self.go_next)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.next_button)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.addWidget(self.stack)
        central_layout.addLayout(nav_layout)
        self.setCentralWidget(central)

        self._update_nav_buttons()

    def go_back(self) -> None:
        self.stack.setCurrentIndex(self.stack.currentIndex() - 1)
        self._update_nav_buttons()

    def go_next(self) -> None:
        self.stack.setCurrentIndex(self.stack.currentIndex() + 1)
        self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        index = self.stack.currentIndex()
        self.back_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < self.stack.count() - 1)
