from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout

from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.core.ros_monitor import MonitorDeployment
from ltlsplitter.gui.pages.base import WizardPage


class DeploymentPage(WizardPage):
    title = "6. Deployment & Live Visualization"
    description = (
        "Deploy the generated monitor against a live ROS2 system and watch violations/state in real time."
    )

    # Real deployments call `on_update` from rclpy's spin thread, not the GUI thread -- routing it
    # through a Qt signal (rather than touching widgets directly) makes that delivery thread-safe,
    # per the libros2qt pattern in docs/pipeline-design-research.md, stage 6.
    _update_received = Signal(str)

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)
        self._deployment: MonitorDeployment | None = None
        self._update_received.connect(self._append_log)

        self.package_label = QLabel()
        self.package_label.setWordWrap(True)
        self.content_layout.addWidget(self.package_label)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("Start Monitoring")
        self.start_button.clicked.connect(self._on_start_clicked)
        self.stop_button = QPushButton("Stop Monitoring")
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        button_row.addStretch()
        self.content_layout.addLayout(button_row)

        self.content_layout.addWidget(QLabel("Violations / state updates:"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.content_layout.addWidget(self.log)

    def on_show(self) -> None:
        if self.state.generated_monitor_path:
            self.package_label.setText(f"Monitor package: {self.state.generated_monitor_path}")
        else:
            self.package_label.setText("(no monitor generated yet -- go back to stage 5)")

    def _on_start_clicked(self) -> None:
        if self._deployment is not None:
            return
        if not self.state.generated_monitor_path:
            QMessageBox.information(self, "No monitor", "Generate a monitor in stage 5 first.")
            return
        package_dir = Path(self.state.generated_monitor_path)
        deployment = MonitorDeployment(package_dir, self._update_received.emit)
        try:
            deployment.start()
        except NotImplementedError:
            self.log.appendPlainText(
                "Not implemented yet -- this needs a sourced ROS2 environment (rclpy) "
                "(see docs/pipeline-design-research.md, stage 6)."
            )
            return
        except Exception as exc:  # noqa: BLE001 -- surface any deployment failure to the user
            self.log.appendPlainText(f"Failed to start monitor: {exc}")
            return
        self._deployment = deployment
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log.appendPlainText(f"Started monitoring {package_dir}")

    def _on_stop_clicked(self) -> None:
        if self._deployment is None:
            return
        try:
            self._deployment.stop()
        except NotImplementedError:
            pass
        finally:
            self._deployment = None
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.log.appendPlainText("Stopped monitoring.")

    def _append_log(self, text: str) -> None:
        self.log.appendPlainText(text)
