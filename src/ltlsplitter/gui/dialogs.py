"""Pop-up dialogs for page 1: writing/editing a requirement (with an LLM translation from
natural language into pt-/ft-LTL) and declaring a new variable."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ltlsplitter.core.complexity import formula_complexity
from ltlsplitter.core.fret_import import infer_variable_type
from ltlsplitter.core.llm_decompose import MissingAPIKeyError, formalize
from ltlsplitter.core.models import FretRequirement, Variable, VariableRole, VariableType
from ltlsplitter.core.reference_check import _LTL_KEYWORDS, find_undeclared_references
from ltlsplitter.gui.theme import compact, set_status
from ltlsplitter.gui.worker import run_in_background

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RESERVED_NAMES = _LTL_KEYWORDS | {"TRUE", "FALSE", "xor", "xnor", "mod", "next", "init", "union", "in"}
_FORMULA_STYLE = "font-family: monospace;"


class RequirementDialog(QDialog):
    """Writes a new requirement or edits an existing one. The natural-language text can be sent
    to the LLM ("Translate to LTL") to fill in both formulas, which stay editable -- the LLM
    only drafts them, the user decides what is saved."""

    def __init__(
        self,
        variables: list[Variable],
        existing_reqids: set[str],
        api_key: str = "",
        requirement: FretRequirement | None = None,
        examples: list[FretRequirement] = (),
        child_count: int = 0,
        default_reqid: str = "",
        on_add_variable=None,
        parent=None,
    ):
        super().__init__(parent)
        self._variables = variables
        self._declared = {v.name for v in variables}
        self._existing_reqids = existing_reqids
        self._api_key = api_key
        self._examples = list(examples)
        self._is_new = requirement is None
        self._llm_thread = None
        self._on_add_variable = on_add_variable
        self.setWindowTitle("New requirement" if self._is_new else f"Edit requirement {requirement.reqid}")
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.reqid_edit = QLineEdit(default_reqid if self._is_new else requirement.reqid)
        if not self._is_new:
            # Renaming would orphan its sub-formulas (they point at it via parent_reqid).
            self.reqid_edit.setReadOnly(True)
        form.addRow("Requirement id:", self.reqid_edit)

        self.text_edit = QPlainTextEdit("" if self._is_new else requirement.fulltext)
        self.text_edit.setPlaceholderText(
            "e.g. While the robot is in state 2, it shall halt and raise the alert."
        )
        self.text_edit.setFixedHeight(90)
        form.addRow("Natural language:", self.text_edit)
        layout.addLayout(form)

        translate_row = QHBoxLayout()
        self.translate_button = compact(QPushButton("Translate to LTL (LLM)"))
        self.translate_button.setToolTip(
            "Sends the text and the declared variables to the LLM, which fills in the ptLTL and "
            "ftLTL fields below. Review them before saving."
        )
        self.translate_button.clicked.connect(self._on_translate_clicked)
        translate_row.addWidget(self.translate_button)
        if on_add_variable is not None:
            add_variable_button = compact(QPushButton("Add Variable..."))
            add_variable_button.setToolTip("Declare a variable the requirement needs (saved right away).")
            add_variable_button.clicked.connect(self._on_add_variable_clicked)
            translate_row.addWidget(add_variable_button)
        translate_row.addStretch()
        layout.addLayout(translate_row)

        self.notes_label = QLabel()
        self.notes_label.setWordWrap(True)
        layout.addWidget(self.notes_label)

        layout.addWidget(QLabel("ptLTL (past-time):"))
        self.pt_edit = QPlainTextEdit("" if self._is_new else requirement.pt_formula)
        self.pt_edit.setStyleSheet(_FORMULA_STYLE)
        layout.addWidget(self.pt_edit)

        layout.addWidget(QLabel("ftLTL (future-time):"))
        self.ft_edit = QPlainTextEdit("" if self._is_new else requirement.ft_formula)
        self.ft_edit.setStyleSheet(_FORMULA_STYLE)
        layout.addWidget(self.ft_edit)

        self.check_label = QLabel()
        self.check_label.setWordWrap(True)
        layout.addWidget(self.check_label)

        if child_count:
            warning = QLabel(
                f"This requirement has {child_count} sub-formula(s). They were checked against "
                "the old formula -- re-run the validation on page 2 after changing it."
            )
            warning.setWordWrap(True)
            set_status(warning, "danger")
            layout.addWidget(warning)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.pt_edit.textChanged.connect(self._refresh_check)
        self.ft_edit.textChanged.connect(self._refresh_check)
        self._refresh_check()

    # -- values -------------------------------------------------------------------------

    def reqid(self) -> str:
        return self.reqid_edit.text().strip()

    def fulltext(self) -> str:
        return self.text_edit.toPlainText().strip()

    def pt_formula(self) -> str:
        return " ".join(self.pt_edit.toPlainText().split())

    def ft_formula(self) -> str:
        return " ".join(self.ft_edit.toPlainText().split())

    def validation_error(self) -> str | None:
        reqid = self.reqid()
        if not reqid:
            return "Give the requirement an id."
        if self._is_new and reqid in self._existing_reqids:
            return f"A requirement called '{reqid}' already exists."
        if not self.pt_formula() and not self.ft_formula():
            return "Write at least one formula, or translate the natural-language text first."
        return None

    def accept(self) -> None:
        error = self.validation_error()
        if error:
            QMessageBox.warning(self, "Can't save yet", error)
            return
        super().accept()

    # -- live checks / LLM -------------------------------------------------------------

    def _undeclared(self) -> list[str]:
        undeclared = []
        for name in find_undeclared_references(self.pt_formula() + " " + self.ft_formula(), self._declared):
            if name not in undeclared:
                undeclared.append(name)
        return undeclared

    def _on_add_variable_clicked(self) -> None:
        """Pre-fills the first identifier the formulas use but nobody declared yet."""
        undeclared = self._undeclared()
        var = self._on_add_variable(undeclared[0] if undeclared else "")
        if var is not None:
            self._variables = [*self._variables, var]
            self._declared.add(var.name)
            self._refresh_check()

    def _refresh_check(self) -> None:
        pt, ft = self.pt_formula(), self.ft_formula()
        undeclared = self._undeclared()
        complexity = " | ".join(
            f"{label} {formula_complexity(f, self._declared).score:g}" for label, f in (("pt", pt), ("ft", ft)) if f
        )
        if undeclared:
            set_status(self.check_label, "danger")
            text = "Possibly undeclared: " + ", ".join(undeclared) + " (add them with 'Add Variable...')"
        else:
            set_status(self.check_label, "success" if (pt or ft) else None)
            text = "All referenced identifiers are declared variables." if (pt or ft) else ""
        if complexity:
            text += f"  Complexity: {complexity}"
        self.check_label.setText(text)

    def _on_translate_clicked(self) -> None:
        text = self.fulltext()
        if not text:
            QMessageBox.information(self, "Nothing to translate", "Write the requirement in natural language first.")
            return
        self.notes_label.setText("Asking the LLM to translate…")
        set_status(self.notes_label, None)
        variables, examples, api_key = self._variables, self._examples, self._api_key

        def _done(result, exc) -> None:
            self._llm_thread = None
            self._on_translation_ready(result, exc)

        self._llm_thread = run_in_background(
            self, lambda: formalize(text, variables, examples, api_key=api_key), _done,
            busy_widgets=(self.translate_button, self.buttons),
        )

    def _on_translation_ready(self, result, exc) -> None:
        if exc is not None:
            self.notes_label.clear()
            if isinstance(exc, MissingAPIKeyError):
                QMessageBox.information(self, "API key needed", str(exc))
            else:
                QMessageBox.critical(self, "Translation failed", f"Couldn't translate the requirement: {exc}")
            return
        self.pt_edit.setPlainText(result.pt_formula)
        self.ft_edit.setPlainText(result.ft_formula)
        if result.notes:
            set_status(self.notes_label, None)
            self.notes_label.setText(f"LLM notes: {result.notes}")
        else:
            set_status(self.notes_label, "success")
            self.notes_label.setText("Translated -- review both formulas before saving.")


_TYPE_CHOICES = (
    (VariableType.BOOL, "Boolean"),
    (VariableType.INT, "Integer"),
    (VariableType.FLOAT, "Float (double)"),
    (VariableType.ENUM, "Enum"),
)
_ROLE_CHOICES = (
    (VariableRole.INPUT, "Input (environment)"),
    (VariableRole.OUTPUT, "Output (system)"),
    (VariableRole.INTERNAL, "Internal (defined by an expression)"),
)


def _parse_optional_number(text: str) -> float | None:
    text = text.strip()
    return float(text) if text else None


class VariableDialog(QDialog):
    """Declares a new variable -- or, given `variable`, edits an existing one -- with the
    parameters the rest of the pipeline needs: type and role (realizability, Ogma), a range or
    enum values (the SMV/Kind2 encodings), the defining expressions for an internal variable
    (equivalence checks and Copilot), and the ROS topic the monitor subscribes to.

    `formulas` (every requirement's pt/ft text) lets it warn when the chosen type contradicts
    how the requirements use the variable -- the mismatch that makes nuXmv reject "! x"."""

    def __init__(
        self,
        existing_names: set[str],
        suggested_name: str = "",
        variable: Variable | None = None,
        formulas: list[str] = (),
        parent=None,
    ):
        super().__init__(parent)
        self._is_edit = variable is not None
        self._existing_names = existing_names - ({variable.name} if variable else set())
        self._formulas = list(formulas)
        self.setWindowTitle(f"Edit variable {variable.name}" if self._is_edit else "Add variable")
        self.resize(520, 0)

        layout = QVBoxLayout(self)
        self.form = QFormLayout()

        self.name_edit = QLineEdit(suggested_name)
        self.form.addRow("Name:", self.name_edit)

        self.type_combo = QComboBox()
        for value, label in _TYPE_CHOICES:
            self.type_combo.addItem(label, value)
        self.form.addRow("Type:", self.type_combo)

        self.role_combo = QComboBox()
        for value, label in _ROLE_CHOICES:
            self.role_combo.addItem(label, value)
        self.form.addRow("Role:", self.role_combo)

        self.min_edit = QLineEdit()
        self.min_edit.setPlaceholderText("optional")
        self.max_edit = QLineEdit()
        self.max_edit.setPlaceholderText("optional")
        self.form.addRow("Minimum:", self.min_edit)
        self.form.addRow("Maximum:", self.max_edit)

        self.enum_edit = QLineEdit()
        self.enum_edit.setPlaceholderText("comma-separated, e.g. idle, running, done")
        self.form.addRow("Enum values:", self.enum_edit)

        self.assignment_edit = QLineEdit()
        self.assignment_edit.setPlaceholderText("e.g. distance_to_target > 3")
        self.form.addRow("Assignment (SMV):", self.assignment_edit)
        self.copilot_assignment_edit = QLineEdit()
        self.copilot_assignment_edit.setPlaceholderText("e.g. distance_to_target > constant 3")
        self.form.addRow("Assignment (Copilot):", self.copilot_assignment_edit)

        self.topic_edit = QLineEdit()
        self.form.addRow("ROS topic:", self.topic_edit)
        layout.addLayout(self.form)

        self.usage_label = QLabel()
        self.usage_label.setWordWrap(True)
        layout.addWidget(self.usage_label)

        if variable is not None:
            # Renaming would leave every formula that mentions it pointing at nothing.
            self.name_edit.setText(variable.name)
            self.name_edit.setReadOnly(True)
            self.name_edit.setToolTip("A variable can't be renamed here -- the formulas refer to it by name.")
            self.type_combo.setCurrentIndex(self.type_combo.findData(variable.type))
            self.role_combo.setCurrentIndex(self.role_combo.findData(variable.role))
            self.min_edit.setText("" if variable.min_value is None else f"{variable.min_value:g}")
            self.max_edit.setText("" if variable.max_value is None else f"{variable.max_value:g}")
            self.enum_edit.setText(", ".join(variable.enum_values))
            self.assignment_edit.setText(variable.assignment or "")
            self.copilot_assignment_edit.setText(variable.copilot_assignment or "")
            self.topic_edit.setText("" if variable.topic == f"/{variable.name}" else variable.topic)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save" if self._is_edit else "Add")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.type_combo.currentIndexChanged.connect(self._refresh_visible_fields)
        self.role_combo.currentIndexChanged.connect(self._refresh_visible_fields)
        self.name_edit.textChanged.connect(self._refresh_visible_fields)
        self._refresh_visible_fields()

    def _refresh_visible_fields(self) -> None:
        var_type = self.type_combo.currentData()
        role = self.role_combo.currentData()
        numeric = var_type in (VariableType.INT, VariableType.FLOAT)
        for widget, visible in (
            (self.min_edit, numeric),
            (self.max_edit, numeric),
            (self.enum_edit, var_type == VariableType.ENUM),
            (self.assignment_edit, role == VariableRole.INTERNAL),
            (self.copilot_assignment_edit, role == VariableRole.INTERNAL),
            # An internal variable is computed inside the monitor, not subscribed to.
            (self.topic_edit, role != VariableRole.INTERNAL),
        ):
            self.form.setRowVisible(widget, visible)
        self.topic_edit.setPlaceholderText(f"/{self.name_edit.text().strip() or 'name'} (default)")
        self._refresh_usage_warning()

    def _refresh_usage_warning(self) -> None:
        name = self.name_edit.text().strip()
        if not name or not _IDENTIFIER_RE.fullmatch(name):
            self.usage_label.clear()
            return
        used_in = [f for f in self._formulas if re.search(rf"\b{re.escape(name)}\b", f)]
        if not used_in:
            self.usage_label.clear()
            return
        usage = infer_variable_type(name, used_in)
        chosen = self.type_combo.currentData()
        if usage == VariableType.BOOL and chosen != VariableType.BOOL:
            set_status(self.usage_label, "danger")
            self.usage_label.setText(
                f"The requirements use {name} only as a truth value (e.g. \"! {name}\"), never in a "
                "comparison -- as a number the model checkers will reject those formulas."
            )
        elif usage != VariableType.BOOL and chosen == VariableType.BOOL:
            set_status(self.usage_label, "danger")
            self.usage_label.setText(
                f"The requirements compare {name} with a number -- as a boolean the model "
                "checkers will reject those comparisons."
            )
        else:
            self.usage_label.clear()

    def validation_error(self) -> str | None:
        name = self.name_edit.text().strip()
        if not _IDENTIFIER_RE.fullmatch(name):
            return "The name must be an identifier: letters, digits and _, not starting with a digit."
        if name in _RESERVED_NAMES:
            return f"'{name}' is an LTL keyword or constant and can't be a variable name."
        if name in self._existing_names:
            return f"A variable called '{name}' already exists."
        var_type = self.type_combo.currentData()
        if var_type in (VariableType.INT, VariableType.FLOAT):
            try:
                lo, hi = _parse_optional_number(self.min_edit.text()), _parse_optional_number(self.max_edit.text())
            except ValueError:
                return "Minimum and maximum must be numbers (or left empty)."
            if lo is not None and hi is not None and lo > hi:
                return "Minimum is larger than maximum."
            if var_type == VariableType.INT and any(v is not None and v != int(v) for v in (lo, hi)):
                return "An integer variable needs whole-number bounds."
        if var_type == VariableType.ENUM:
            values = self._enum_values()
            if not values:
                return "An enum variable needs at least one value."
            bad = [v for v in values if not _IDENTIFIER_RE.fullmatch(v)]
            if bad:
                return "Enum values must be identifiers: " + ", ".join(bad)
            if len(set(values)) != len(values):
                return "Enum values must be distinct."
        if self.role_combo.currentData() == VariableRole.INTERNAL and not self.assignment_edit.text().strip():
            return "An internal variable needs its defining expression (Assignment (SMV))."
        return None

    def _enum_values(self) -> list[str]:
        return [v.strip() for v in self.enum_edit.text().split(",") if v.strip()]

    def accept(self) -> None:
        error = self.validation_error()
        if error:
            QMessageBox.warning(self, "Can't save the variable yet" if self._is_edit else "Can't add the variable yet", error)
            return
        super().accept()

    def variable(self) -> Variable:
        var_type = self.type_combo.currentData()
        role = self.role_combo.currentData()
        numeric = var_type in (VariableType.INT, VariableType.FLOAT)
        internal = role == VariableRole.INTERNAL
        name = self.name_edit.text().strip()
        return Variable(
            name=name,
            type=var_type,
            role=role,
            topic="" if internal else (self.topic_edit.text().strip() or f"/{name}"),
            min_value=_parse_optional_number(self.min_edit.text()) if numeric else None,
            max_value=_parse_optional_number(self.max_edit.text()) if numeric else None,
            enum_values=self._enum_values() if var_type == VariableType.ENUM else [],
            assignment=self.assignment_edit.text().strip() or None if internal else None,
            copilot_assignment=self.copilot_assignment_edit.text().strip() or None if internal else None,
        )


_TYPE_LABELS = dict(_TYPE_CHOICES)
_ROLE_LABELS = {VariableRole.INPUT: "Input", VariableRole.OUTPUT: "Output", VariableRole.INTERNAL: "Internal"}
_TABLE_COLUMNS = ("Name", "Type", "Role", "Range / values", "Assignment", "ROS topic", "Used by")


def _range_text(var: Variable) -> str:
    if var.type == VariableType.ENUM:
        return "{" + ", ".join(var.enum_values) + "}" if var.enum_values else ""
    if var.min_value is None and var.max_value is None:
        return ""
    lo = "" if var.min_value is None else f"{var.min_value:g}"
    hi = "" if var.max_value is None else f"{var.max_value:g}"
    return f"{lo} .. {hi}"


class VariableTableDialog(QDialog):
    """Every declared variable in one table, with Add Variable and Edit Variable (both through
    VariableDialog). `get_variables`/`get_requirements` are read again after every change,
    because a save reloads the project from disk (new objects); `on_add`/`on_edit` do the
    change-and-save and return whether anything changed."""

    def __init__(self, get_variables, get_requirements, on_add, on_edit, parent=None):
        super().__init__(parent)
        self._get_variables = get_variables
        self._get_requirements = get_requirements
        self._on_add = on_add
        self._on_edit = on_edit
        self.setWindowTitle("Variables")
        self.resize(960, 520)

        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, len(_TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(_TABLE_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self._on_edit_clicked())
        layout.addWidget(self.table)

        row = QHBoxLayout()
        self.add_button = compact(QPushButton("Add Variable..."))
        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button = compact(QPushButton("Edit Variable..."))
        self.edit_button.setToolTip("Edit the selected variable (or double-click its row).")
        self.edit_button.clicked.connect(self._on_edit_clicked)
        row.addWidget(self.add_button)
        row.addWidget(self.edit_button)
        row.addStretch()
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.rejected.connect(self.reject)
        row.addWidget(close_buttons)
        layout.addLayout(row)

        self.refresh()

    def refresh(self, select_name: str | None = None) -> None:
        variables = self._get_variables()
        requirements = self._get_requirements()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(variables))
        for row, var in enumerate(variables):
            used_by = sum(1 for r in requirements if var.name in r.variable_names)
            assignment = var.assignment or ""
            cells = (
                var.name, _TYPE_LABELS.get(var.type, var.type.value), _ROLE_LABELS.get(var.role, var.role.value),
                _range_text(var), assignment,
                "" if var.role == VariableRole.INTERNAL else (var.topic or f"/{var.name}"),
                str(used_by),
            )
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == len(cells) - 1:
                    item.setData(Qt.ItemDataRole.DisplayRole, used_by)  # sorts numerically
                item.setData(Qt.ItemDataRole.UserRole, var.name)
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.summary_label.setText(
            f"{len(variables)} variable(s). Double-click a row to edit it."
            if variables else "No variables declared yet."
        )
        self.edit_button.setEnabled(bool(variables))
        if select_name:
            self.select(select_name)

    def select(self, name: str) -> None:
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == name:
                self.table.selectRow(row)
                return

    def selected_name(self) -> str | None:
        items = self.table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _on_add_clicked(self) -> None:
        var = self._on_add()
        if var is not None:
            self.refresh(select_name=var.name)

    def _on_edit_clicked(self) -> None:
        name = self.selected_name()
        if name is None:
            QMessageBox.information(self, "Nothing selected", "Select a variable in the table first.")
            return
        if self._on_edit(name):
            self.refresh(select_name=name)
