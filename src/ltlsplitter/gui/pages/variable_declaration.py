from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ltlsplitter.core.models import Variable, VariableRole, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.base import WizardPage

_RANGE_TYPES = (VariableType.INT, VariableType.FLOAT)
_SPIN_RANGE = 1_000_000.0


class VariableDeclarationPage(WizardPage):
    title = "2. Variable Declaration"
    description = "Declare the variables used in your requirements: name, type, range, and associated ROS node."

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems([t.value for t in VariableType])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self.role_combo = QComboBox()
        self.role_combo.addItems([r.value for r in VariableRole])
        self.role_combo.setToolTip(
            "Input: set by the environment/another node (read-only to the monitor).\n"
            "Output: set by the system under monitoring -- needed for realizability checks."
        )
        self.ros_node_edit = QLineEdit()
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-_SPIN_RANGE, _SPIN_RANGE)
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-_SPIN_RANGE, _SPIN_RANGE)
        self.max_spin.setValue(_SPIN_RANGE)
        self.enum_values_edit = QLineEdit()
        self.enum_values_edit.setPlaceholderText("comma-separated values")

        form.addRow("Name", self.name_edit)
        form.addRow("Type", self.type_combo)
        form.addRow("Role", self.role_combo)
        form.addRow("ROS Node", self.ros_node_edit)
        form.addRow("Min", self.min_spin)
        form.addRow("Max", self.max_spin)
        form.addRow("Enum values", self.enum_values_edit)
        self.content_layout.addLayout(form)

        add_button = QPushButton("Add Variable")
        add_button.clicked.connect(self._on_add_variable)
        self.content_layout.addWidget(add_button)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Role", "Range/Values", "ROS Node"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.content_layout.addWidget(self.table)

        remove_row = QHBoxLayout()
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self._on_remove_selected)
        remove_row.addStretch()
        remove_row.addWidget(remove_button)
        self.content_layout.addLayout(remove_row)

        self._on_type_changed(self.type_combo.currentText())
        self._refresh_table()

    def _on_type_changed(self, type_value: str) -> None:
        is_range_type = type_value in (VariableType.INT.value, VariableType.FLOAT.value)
        is_enum_type = type_value == VariableType.ENUM.value
        self.min_spin.setEnabled(is_range_type)
        self.max_spin.setEnabled(is_range_type)
        self.enum_values_edit.setEnabled(is_enum_type)

    def _on_add_variable(self) -> None:
        name = self.name_edit.text().strip()
        ros_node = self.ros_node_edit.text().strip()
        if not name or not ros_node:
            QMessageBox.warning(self, "Missing fields", "Name and ROS node are required.")
            return
        var_type = VariableType(self.type_combo.currentText())
        role = VariableRole(self.role_combo.currentText())

        variable = Variable(name=name, type=var_type, ros_node=ros_node, role=role)
        if var_type in _RANGE_TYPES:
            variable.min_value = self.min_spin.value()
            variable.max_value = self.max_spin.value()
        elif var_type == VariableType.ENUM:
            variable.enum_values = [v.strip() for v in self.enum_values_edit.text().split(",") if v.strip()]

        self.state.variables.append(variable)
        self._refresh_table()
        self.name_edit.clear()
        self.ros_node_edit.clear()
        self.enum_values_edit.clear()

    def _on_remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            del self.state.variables[row]
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.state.variables))
        for row, variable in enumerate(self.state.variables):
            if variable.type in _RANGE_TYPES:
                range_text = f"{variable.min_value} .. {variable.max_value}"
            elif variable.type == VariableType.ENUM:
                range_text = ", ".join(variable.enum_values)
            else:
                range_text = ""
            self.table.setItem(row, 0, QTableWidgetItem(variable.name))
            self.table.setItem(row, 1, QTableWidgetItem(variable.type.value))
            self.table.setItem(row, 2, QTableWidgetItem(variable.role.value))
            self.table.setItem(row, 3, QTableWidgetItem(range_text))
            self.table.setItem(row, 4, QTableWidgetItem(variable.ros_node))
