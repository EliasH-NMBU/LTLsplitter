from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ltlsplitter.core.ogma import generate_ros2_monitor
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.base import WizardPage


class MonitorGenerationPage(WizardPage):
    title = "5. Monitor Generation"
    description = "Generate ROS2 runtime monitors from the validated spec via NASA's Ogma."

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)
        self._current_requirement_id: str | None = None

        body = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("Requirements with specs:"))
        self.requirement_list = QListWidget()
        self.requirement_list.itemSelectionChanged.connect(self._on_requirement_selected)
        left.addWidget(self.requirement_list)
        body.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Output directory:"))
        dir_row = QHBoxLayout()
        self.output_dir_label = QLabel("(none selected)")
        self.output_dir_label.setWordWrap(True)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_clicked)
        dir_row.addWidget(self.output_dir_label, 1)
        dir_row.addWidget(browse_button)
        right.addLayout(dir_row)

        generate_button = QPushButton("Generate Monitor")
        generate_button.clicked.connect(self._on_generate_clicked)
        right.addWidget(generate_button)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        right.addWidget(self.status_label)

        right.addStretch()
        body.addLayout(right, 1)
        self.content_layout.addLayout(body)

        self._output_dir: Path | None = None

    def on_show(self) -> None:
        self._refresh_requirement_list()
        if self.state.generated_monitor_path:
            self.status_label.setStyleSheet("color: #1a7f37;")
            self.status_label.setText(f"Last generated monitor: {self.state.generated_monitor_path}")

    def _refresh_requirement_list(self) -> None:
        previously_selected = self._current_requirement_id

        self.requirement_list.blockSignals(True)
        self.requirement_list.clear()
        for requirement_id in self.state.requirement_ids():
            spec = self.state.specifications.get(requirement_id)
            if spec and spec.ltl_formula and spec.ltl_formula.strip():
                item = QListWidgetItem(f"{requirement_id}: {spec.ltl_formula}")
                item.setData(Qt.ItemDataRole.UserRole, requirement_id)
                self.requirement_list.addItem(item)
        self.requirement_list.blockSignals(False)

        if self.requirement_list.count() == 0:
            self._current_requirement_id = None
            return

        target_row = 0
        for row in range(self.requirement_list.count()):
            if self.requirement_list.item(row).data(Qt.ItemDataRole.UserRole) == previously_selected:
                target_row = row
                break
        self.requirement_list.setCurrentRow(target_row)

    def _on_requirement_selected(self) -> None:
        items = self.requirement_list.selectedItems()
        self._current_requirement_id = items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _on_browse_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select output directory")
        if directory:
            self._output_dir = Path(directory)
            self.output_dir_label.setText(directory)

    def _on_generate_clicked(self) -> None:
        if self._current_requirement_id is None:
            QMessageBox.information(
                self, "No requirement selected", "Author and select a spec with an LTL formula first."
            )
            return
        if self._output_dir is None:
            QMessageBox.information(self, "No output directory", "Choose an output directory first.")
            return
        spec = self.state.specifications[self._current_requirement_id]
        try:
            package_dir = generate_ros2_monitor(spec, self._output_dir)
        except NotImplementedError:
            self.status_label.setStyleSheet("color: #666;")
            self.status_label.setText(
                "Not implemented yet -- this needs Ogma (github.com/nasa/ogma) installed, which "
                "requires GHC/Cabal/Z3 (see docs/pipeline-design-research.md, stage 5)."
            )
            return
        except Exception as exc:  # noqa: BLE001 -- surface any ogma subprocess failure to the user
            self.status_label.setStyleSheet("color: #b00020;")
            self.status_label.setText(f"Generation failed: {exc}")
            return
        self.state.generated_monitor_path = str(package_dir)
        self.status_label.setStyleSheet("color: #1a7f37;")
        self.status_label.setText(f"Generated monitor package at {package_dir}")
