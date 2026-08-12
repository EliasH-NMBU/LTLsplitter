from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QProcess, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout

from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.core.ros_monitor import MonitorDeployment, ToolNotFoundError
from ltlsplitter.gui.pages.base import WizardPage

_ROS_SETUP_BASH = os.environ.get("ROS_SETUP_BASH", "/opt/ros/lyrical/setup.bash")
_LTL_DEMO_WS_SETUP_BASH = os.environ.get(
    "LTL_DEMO_WS_SETUP_BASH", str(Path.home() / "ltl_demo_ws" / "install" / "setup.bash")
)


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
        self._sim_process: QProcess | None = None

        self.content_layout.addWidget(QLabel("Demo ROS2 system (TurtleBot3 + Gazebo, human detection, safety stop):"))
        sim_row = QHBoxLayout()
        self.launch_sim_button = QPushButton("Launch Simulation")
        self.launch_sim_button.clicked.connect(self._on_launch_sim_clicked)
        self.stop_sim_button = QPushButton("Stop Simulation")
        self.stop_sim_button.clicked.connect(self._on_stop_sim_clicked)
        self.stop_sim_button.setEnabled(False)
        sim_row.addWidget(self.launch_sim_button)
        sim_row.addWidget(self.stop_sim_button)
        sim_row.addStretch()
        self.content_layout.addLayout(sim_row)

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
        self.log.appendPlainText(f"Building and starting the monitor for {package_dir} -- this can take a minute...")
        try:
            deployment.start()
        except ToolNotFoundError as exc:
            self.log.appendPlainText(str(exc))
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
        except ToolNotFoundError:
            pass
        finally:
            self._deployment = None
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.log.appendPlainText("Stopped monitoring.")

    def _on_launch_sim_clicked(self) -> None:
        if self._sim_process is not None:
            return
        if not Path(_LTL_DEMO_WS_SETUP_BASH).is_file():
            QMessageBox.information(
                self, "Demo workspace not found",
                f"No sourced workspace at {_LTL_DEMO_WS_SETUP_BASH}. Build the ltl_demo "
                "package first (see README.md), or set LTL_DEMO_WS_SETUP_BASH.",
            )
            return
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: self._on_sim_output(process))
        process.finished.connect(self._on_sim_finished)
        command = (
            f"source {_ROS_SETUP_BASH} && source {_LTL_DEMO_WS_SETUP_BASH} && "
            "exec ros2 launch ltl_demo demo.launch.py"
        )
        process.start("bash", ["-c", command])
        self._sim_process = process
        self.launch_sim_button.setEnabled(False)
        self.stop_sim_button.setEnabled(True)
        self.log.appendPlainText("Launching simulation (Gazebo window should open shortly)...")

    def _on_stop_sim_clicked(self) -> None:
        if self._sim_process is None:
            return
        self._sim_process.terminate()
        if not self._sim_process.waitForFinished(5000):
            self._sim_process.kill()
        self._sim_process = None
        self.launch_sim_button.setEnabled(True)
        self.stop_sim_button.setEnabled(False)
        self.log.appendPlainText("Stopped simulation.")

    def _on_sim_output(self, process: QProcess) -> None:
        text = bytes(process.readAllStandardOutput()).decode(errors="replace")
        for line in text.splitlines():
            if line.strip():
                self.log.appendPlainText(f"[sim] {line}")

    def _on_sim_finished(self) -> None:
        self._sim_process = None
        self.launch_sim_button.setEnabled(True)
        self.stop_sim_button.setEnabled(False)
        self.log.appendPlainText("Simulation process exited.")

    def _append_log(self, text: str) -> None:
        self.log.appendPlainText(text)
