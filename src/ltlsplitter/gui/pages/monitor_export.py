from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton

from ltlsplitter.core.models import Specification
from ltlsplitter.core.ogma import ToolNotFoundError, generate_ros2_monitor
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.base import WizardPage


class MonitorExportPage(WizardPage):
    title = "4. Ogma/Copilot Export"
    description = "Generate a ROS2 Copilot runtime-verification monitor via NASA's Ogma, one property per accepted sub-formula."

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)

        self.content_layout.addWidget(QLabel("Formula(s) to export:"))
        self.formulas_label = QLabel()
        self.formulas_label.setWordWrap(True)
        self.content_layout.addWidget(self.formulas_label)

        self.content_layout.addWidget(QLabel("Output directory:"))
        dir_row = QHBoxLayout()
        self.output_dir_label = QLabel("(none selected)")
        self.output_dir_label.setWordWrap(True)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_clicked)
        dir_row.addWidget(self.output_dir_label, 1)
        dir_row.addWidget(browse_button)
        self.content_layout.addLayout(dir_row)

        generate_button = QPushButton("Generate Monitor")
        generate_button.clicked.connect(self._on_generate_clicked)
        self.content_layout.addWidget(generate_button)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.content_layout.addWidget(self.status_label)

        self.content_layout.addStretch()

        self._output_dir: Path | None = None

    def on_show(self) -> None:
        sub_formulas = self.state.active_sub_formulas()
        if sub_formulas:
            self.formulas_label.setText("\n".join(f"{s.id}: {s.pt_formula}" for s in sub_formulas))
        else:
            self.formulas_label.setText("(select a requirement on page 1 first)")
        if self.state.generated_monitor_path:
            self.status_label.setStyleSheet("color: #1a7f37;")
            self.status_label.setText(f"Last generated monitor: {self.state.generated_monitor_path}")

    def _on_browse_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select output directory")
        if directory:
            self._output_dir = Path(directory)
            self.output_dir_label.setText(directory)

    def _on_generate_clicked(self) -> None:
        sub_formulas = self.state.active_sub_formulas()
        if not sub_formulas:
            QMessageBox.information(self, "Nothing to export", "Select a requirement on page 1 first.")
            return
        if self._output_dir is None:
            QMessageBox.information(self, "No output directory", "Choose an output directory first.")
            return

        specs = [Specification(requirement_id=s.id, ltl_formula=s.pt_formula) for s in sub_formulas]
        variables = self.state.fret_import.variables if self.state.fret_import else []
        try:
            package_dir = generate_ros2_monitor(specs, self._output_dir, variables)
        except ToolNotFoundError as exc:
            self.status_label.setStyleSheet("color: #666;")
            self.status_label.setText(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- surface any ogma subprocess failure to the user
            self.status_label.setStyleSheet("color: #b00020;")
            self.status_label.setText(f"Generation failed: {exc}")
            return

        self.state.generated_monitor_path = str(package_dir)
        self.status_label.setStyleSheet("color: #1a7f37;")
        self.status_label.setText(f"Generated monitor package at {package_dir}")
