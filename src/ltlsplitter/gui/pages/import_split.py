from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ltlsplitter.core.complexity import formula_complexity
from ltlsplitter.core.fret_import import (
    InvalidFretFileError,
    import_fret_file,
    referenced_variable_names,
    save_session,
)
from ltlsplitter.core.llm_decompose import MissingAPIKeyError, decompose, suggest_split
from ltlsplitter.core.models import FretImport, FretRequirement, SubFormula, Variable
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.core.reference_check import find_undeclared_references
from ltlsplitter.core.smv_import import InvalidSmvFileError, import_smv_file
from ltlsplitter.gui.dialogs import RequirementDialog, VariableDialog, VariableTableDialog
from ltlsplitter.gui.pages.base import WizardPage
from ltlsplitter.gui.theme import compact, set_status, theme_manager
from ltlsplitter.gui.worker import run_in_background

_SETTINGS_ORG = "LTLsplitter"
_SETTINGS_APP = "LTLsplitter"
_API_KEY_SETTING = "anthropic/api_key"
_EXPORTS_DIR_NAME = "ltlsplitter_exports"
_FORMULA_VIEW_SETTING = "split/formula_view"

# Which LTL flavour the split page shows: FRET gives every requirement both a past-time and a
# future-time formula, and showing both side by side makes long formulas hard to read.
_FORMULA_VIEWS = (("pt", "ptLTL"), ("ft", "ftLTL"), ("both", "Both"))
_FORMULA_STYLE = "font-family: monospace;"
_STYLE_EXAMPLE_COUNT = 3


class _SearchHighlightDelegate(QStyledItemDelegate):
    """Paints a row's background directly, bypassing QTreeWidgetItem.setBackground() --
    confirmed (by rendering the real widget off-screen and sampling pixels, not just reading
    back what was set) that theme.py's global `QTreeWidget::item { ... }` stylesheet rule makes
    Qt silently ignore Qt::BackgroundRole for every item once any rule matches that sub-control,
    so a per-item setBackground() call has no visible effect at all even though
    item.background() still faithfully reports the color that was "set". Reads
    `is_highlighted` fresh on every paint, so the caller only needs to trigger a repaint
    (`tree.viewport().update()`) when the highlighted set changes -- no per-item bookkeeping."""

    def __init__(self, is_highlighted, parent=None):
        super().__init__(parent)
        self._is_highlighted = is_highlighted

    def paint(self, painter, option, index) -> None:
        reqid = index.sibling(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        if reqid is not None and self._is_highlighted(reqid):
            painter.save()
            painter.fillRect(option.rect, QColor(theme_manager.palette.warning_soft))
            painter.restore()
        super().paint(painter, option, index)


class ImportSplitPage(WizardPage):
    title = "1. Import & Split Review"
    description = (
        "Import a FRET project export, or a plain NuSMV/nuXmv .smv file (VAR declarations plus "
        "one or more LTLSPEC statements -- each becomes its own requirement, picked up as "
        "past-time or future-time based on whether it uses any H/O/S/Y/Z operator), pick one "
        "requirement from it, and let an LLM suggest whether it should be split into "
        "independent sub-properties. Review and accept/reject "
        "the suggestion, then have the LLM perform the split -- the sub-formulas are editable "
        "before moving on to validation. Accepting a split saves it as a new copy of the FRET "
        "file (the original is never modified) with the sub-formulas appended as requirements "
        "nested under the original, shown here as a dropdown. New Requirement writes one from "
        "natural language (the LLM drafts the ptLTL/ftLTL), Edit Requirement changes any "
        "requirement's text or formulas, and Variable Table lists every variable, with Add Variable and Edit Variable to declare new ones or change their type, role, range and topic -- each is "
        "saved to the same copy, as is Save for deletions and assumption changes. The Assumption checkbox marks a "
        "requirement as an environment constraint rather than a system guarantee (seeded from "
        "FRET's \"*_assumption\" naming convention, correct it if wrong) -- used by the "
        "realizability check on page 3."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)
        self._llm_thread = None
        self._search_queue: list[FretRequirement] = []
        self._search_busy_widgets: tuple[QPushButton | QTreeWidget, ...] = ()
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)

        api_key_row = QHBoxLayout()
        api_key_row.addWidget(QLabel("Anthropic API key:"))

        self.api_key_edit = QLineEdit(self._settings.value(_API_KEY_SETTING, ""))
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-ant-...")
        self.api_key_edit.textChanged.connect(self._on_api_key_changed)
        self.api_key_edit.editingFinished.connect(self._on_api_key_editing_finished)
        api_key_row.addWidget(self.api_key_edit, 1)

        self.api_key_status_label = QLabel()
        api_key_row.addWidget(self.api_key_status_label, 1)

        self.api_key_change_button = compact(QPushButton())
        self.api_key_change_button.clicked.connect(self._on_api_key_change_clicked)
        api_key_row.addWidget(self.api_key_change_button)

        self.content_layout.addLayout(api_key_row)

        # Once a key is on file, it starts collapsed behind a status label + button -- not
        # sitting visibly (even password-masked) on screen every time this page is shown.
        self._api_key_editing = not bool(self._settings.value(_API_KEY_SETTING, "").strip())
        self._update_api_key_visibility()

        import_row = QHBoxLayout()
        import_button = QPushButton("Import FRET/SMV file...")
        import_button.clicked.connect(self._on_import_clicked)
        self.import_label = QLabel("(no file imported)")
        import_row.addWidget(import_button)
        import_row.addWidget(self.import_label, 1)
        self.content_layout.addLayout(import_row)

        edit_row = QHBoxLayout()
        self.new_requirement_button = QPushButton("New Requirement...")
        self.new_requirement_button.setToolTip(
            "Write a requirement in natural language and let the LLM define it in ptLTL and ftLTL."
        )
        self.new_requirement_button.clicked.connect(self._on_new_requirement_clicked)
        self.edit_requirement_button = QPushButton("Edit Requirement...")
        self.edit_requirement_button.setToolTip("Change the selected requirement's text or formulas.")
        self.edit_requirement_button.clicked.connect(self._on_edit_requirement_clicked)
        self.variable_table_button = QPushButton("Variable Table...")
        self.variable_table_button.setToolTip(
            "Show every variable, add new ones and edit existing ones (type, role, range, topic, ...)."
        )
        self.variable_table_button.clicked.connect(self._on_variable_table_clicked)
        self.save_button = QPushButton("Save")
        self.save_button.setToolTip(
            "Write the whole session (edits, new requirements and variables, deletions, "
            "assumption flags) to the save file. The original import is never modified."
        )
        self.save_button.clicked.connect(lambda: self._save_session())
        self.save_status_label = QLabel()
        for widget in (self.new_requirement_button, self.edit_requirement_button, self.variable_table_button, self.save_button):
            edit_row.addWidget(widget)
        edit_row.addWidget(self.save_status_label, 1)
        self.content_layout.addLayout(edit_row)

        body = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("Requirements in file (splits nested under their original):"))

        assumption_actions_row = QHBoxLayout()
        select_all_button = QPushButton("Select All")
        select_all_button.setToolTip("Mark every requirement as an environment assumption.")
        select_all_button.clicked.connect(lambda: self._set_all_assumptions(True))
        clear_all_button = QPushButton("Clear All")
        clear_all_button.setToolTip("Mark every requirement as a system guarantee (not an assumption).")
        clear_all_button.clicked.connect(lambda: self._set_all_assumptions(False))
        delete_button = QPushButton("Delete")
        delete_button.setToolTip(
            "Delete the selected requirement from this session -- if it's a split's parent, "
            "its sub-formulas are deleted with it."
        )
        delete_button.clicked.connect(self._on_delete_clicked)
        self.search_button = QPushButton("LTLsplit search")
        self.search_button.setToolTip(
            "Asks the LLM about every requirement in the tree and highlights the ones it "
            "recommends splitting. A highlight clears once that requirement's split is "
            "accepted or rejected."
        )
        self.search_button.clicked.connect(self._on_search_clicked)
        assumption_actions_row.addWidget(select_all_button)
        assumption_actions_row.addWidget(clear_all_button)
        assumption_actions_row.addWidget(delete_button)
        assumption_actions_row.addWidget(self.search_button)
        assumption_actions_row.addStretch()
        left.addLayout(assumption_actions_row)

        self.search_status_label = QLabel()
        self.search_status_label.setWordWrap(True)
        left.addWidget(self.search_status_label)

        self.requirement_tree = QTreeWidget()
        self.requirement_tree.setColumnCount(2)
        self.requirement_tree.setHeaderLabels(["Requirement", "Assumption"])
        self.requirement_tree.setItemDelegate(
            _SearchHighlightDelegate(lambda reqid: reqid in self.state.recommended_split_reqids, self.requirement_tree)
        )
        self.requirement_tree.currentItemChanged.connect(self._on_requirement_selected)
        self.requirement_tree.itemChanged.connect(self._on_assumption_toggled)
        left.addWidget(self.requirement_tree)
        body.addLayout(left, 1)

        right = QVBoxLayout()

        view_row = QHBoxLayout()
        view_row.addWidget(QLabel("Show:"))
        saved_view = self._settings.value(_FORMULA_VIEW_SETTING, "both")
        self.formula_view = saved_view if saved_view in dict(_FORMULA_VIEWS) else "both"
        self.formula_view_group = QButtonGroup(self)
        self.formula_view_buttons: dict[str, QRadioButton] = {}
        for key, text in _FORMULA_VIEWS:
            button = QRadioButton(text)
            button.setChecked(key == self.formula_view)
            button.toggled.connect(lambda checked, k=key: checked and self._set_formula_view(k))
            self.formula_view_group.addButton(button)
            self.formula_view_buttons[key] = button
            view_row.addWidget(button)
        view_row.addStretch()
        right.addLayout(view_row)

        self.formula_heading = QLabel()
        right.addWidget(self.formula_heading)
        self.formula_label = QLabel()
        self.formula_label.setWordWrap(True)
        self.formula_label.setStyleSheet(_FORMULA_STYLE)
        self.formula_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.formula_label)

        right.addWidget(QLabel("Referenced variables:"))
        self.variables_label = QLabel()
        self.variables_label.setWordWrap(True)
        right.addWidget(self.variables_label)

        self.complexity_label = QLabel()
        self.complexity_label.setWordWrap(True)
        self.complexity_label.setToolTip("Complexity = number of operators + 0.5 x number of distinct variables.")
        right.addWidget(self.complexity_label)

        self.suggest_button = compact(QPushButton("Suggest Split (LLM)"))
        self.suggest_button.clicked.connect(self._on_suggest_clicked)
        right.addWidget(self.suggest_button)

        self.suggestion_label = QLabel()
        self.suggestion_label.setWordWrap(True)
        right.addWidget(self.suggestion_label)

        decision_row = QHBoxLayout()
        self.accept_button = compact(QPushButton("Accept split"))
        self.accept_button.clicked.connect(self._on_accept_clicked)
        self.reject_button = compact(QPushButton("Reject (keep original)"))
        self.reject_button.clicked.connect(self._on_reject_clicked)
        self.force_split_button = compact(QPushButton("Force Split"))
        self.force_split_button.clicked.connect(self._on_force_split_clicked)
        self.force_split_button.setVisible(False)
        decision_row.addWidget(self.accept_button)
        decision_row.addWidget(self.reject_button)
        decision_row.addWidget(self.force_split_button)
        decision_row.addStretch()
        right.addLayout(decision_row)

        right.addWidget(QLabel("Sub-formulas (double-click to edit):"))
        self.sub_formula_list = QListWidget()
        self.sub_formula_list.setStyleSheet(_FORMULA_STYLE)
        self.sub_formula_list.setWordWrap(True)
        self.sub_formula_list.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.sub_formula_list.itemChanged.connect(self._on_sub_formula_edited)
        right.addWidget(self.sub_formula_list)

        self.reference_label = QLabel()
        self.reference_label.setWordWrap(True)
        right.addWidget(self.reference_label)

        self.decomposition_complexity_label = QLabel()
        self.decomposition_complexity_label.setWordWrap(True)
        right.addWidget(self.decomposition_complexity_label)

        body.addLayout(right, 2)
        self.content_layout.addLayout(body)
        self._update_formula_heading()

    # -- import / selection ------------------------------------------------------------

    def on_show(self) -> None:
        self._refresh_requirement_tree()

    def _on_api_key_changed(self, text: str) -> None:
        self._settings.setValue(_API_KEY_SETTING, text)
        self._update_api_key_visibility()

    def _on_api_key_editing_finished(self) -> None:
        """Collapses the field back behind the status label once a key has actually been
        entered (Enter pressed, or focus lost) -- an empty field stays in editing mode, since
        there's nothing yet to hide behind a "key set" button."""
        if self.api_key_edit.text().strip():
            self._api_key_editing = False
            self._update_api_key_visibility()

    def _on_api_key_change_clicked(self) -> None:
        self._api_key_editing = True
        self._update_api_key_visibility()
        self.api_key_edit.setFocus()
        self.api_key_edit.selectAll()

    def _update_api_key_visibility(self) -> None:
        has_key = bool(self._settings.value(_API_KEY_SETTING, "").strip())
        self.api_key_edit.setVisible(self._api_key_editing)
        self.api_key_status_label.setVisible(not self._api_key_editing)
        self.api_key_change_button.setVisible(not self._api_key_editing)
        self.api_key_status_label.setText("API key set" if has_key else "No API key set")
        self.api_key_change_button.setText("Change" if has_key else "Set API key")

    def _on_import_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import FRET project export or NuSMV file", "",
            "FRET export / NuSMV file (*.json *.smv);;FRET export (*.json);;NuSMV file (*.smv);;All files (*)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".smv"):
                fret_import = import_smv_file(path)
            else:
                fret_import = import_fret_file(path)
        except (InvalidFretFileError, InvalidSmvFileError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.state.fret_import = fret_import
        self.state.fret_import_path = path
        self.state.session_export_path = ""
        self.state.selected_requirement_id = None
        self.state.recommended_split_reqids = set()
        self.state.search_results = {}
        self.state.split_suggestion = None
        self.state.split_accepted = False
        self.state.sub_formulas = []
        self.force_split_button.setVisible(False)
        self.save_status_label.clear()
        self.search_status_label.clear()
        self.import_label.setText(f"{fret_import.project}: {len(fret_import.requirements)} requirement(s)")
        self._refresh_requirement_tree()

    def _refresh_requirement_tree(self) -> None:
        self.requirement_tree.blockSignals(True)
        self.requirement_tree.clear()
        if self.state.fret_import:
            by_reqid = {req.reqid: req for req in self.state.fret_import.requirements}
            items_by_reqid: dict[str, QTreeWidgetItem] = {}
            # Two passes: create every item first, then nest -- a requirement's parent may be
            # defined later in the file than the requirement itself.
            for req in self.state.fret_import.requirements:
                item = QTreeWidgetItem([req.reqid])
                item.setData(0, Qt.ItemDataRole.UserRole, req.reqid)
                item.setToolTip(0, req.fulltext)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(1, Qt.CheckState.Checked if req.is_assumption else Qt.CheckState.Unchecked)
                items_by_reqid[req.reqid] = item
            for req in self.state.fret_import.requirements:
                item = items_by_reqid[req.reqid]
                parent_item = items_by_reqid.get(req.parent_reqid) if req.parent_reqid in by_reqid else None
                if parent_item is not None:
                    parent_item.addChild(item)
                else:
                    self.requirement_tree.addTopLevelItem(item)
            self.requirement_tree.expandAll()
        self.requirement_tree.blockSignals(False)

        if self.state.selected_requirement_id:
            self._select_requirement_item(self.state.selected_requirement_id)
        self._refresh_formula_display()

    def _select_requirement_item(self, reqid: str) -> None:
        iterator = self.requirement_tree.findItems(reqid, Qt.MatchFlag.MatchRecursive, 0)
        for item in iterator:
            if item.data(0, Qt.ItemDataRole.UserRole) == reqid:
                self.requirement_tree.setCurrentItem(item)
                return

    def _refresh_requirement_tree_highlights(self) -> None:
        """Repaints the tree so rows pick up the current `state.recommended_split_reqids` --
        _SearchHighlightDelegate reads that set fresh on every paint, so nothing needs to be
        recomputed per item here, just a redraw triggered. Used after a single accept/reject
        and, incrementally, during a search batch; a full `_refresh_requirement_tree` rebuild
        already repaints on its own and doesn't need this too."""
        self.requirement_tree.viewport().update()

    def _on_assumption_toggled(self, item: QTreeWidgetItem, column: int) -> None:
        """Flips `is_assumption` on the underlying requirement in memory -- affects the current
        session's realizability checks immediately. Not written to disk right away (that would
        either silently rewrite the active file or require a save dialog on every click); it's
        carried forward automatically the next time a split is saved, via the
        `current_requirements` patch-in in `append_sub_formulas_and_save`."""
        if column != 1 or self.state.fret_import is None:
            return
        reqid = item.data(0, Qt.ItemDataRole.UserRole)
        req = self.state.fret_import.requirement(reqid)
        if req is not None:
            req.is_assumption = item.checkState(1) == Qt.CheckState.Checked

    def _set_all_assumptions(self, value: bool) -> None:
        """Bulk-toggle every requirement's Assumption checkbox at once -- doing this one row at
        a time via `_on_assumption_toggled` doesn't scale to a file with many requirements."""
        if not self.state.fret_import:
            return
        for req in self.state.fret_import.requirements:
            req.is_assumption = value
        self._refresh_requirement_tree()

    def _on_delete_clicked(self) -> None:
        if not self.state.fret_import:
            return
        req = self._selected_requirement()
        if req is None:
            QMessageBox.information(self, "Nothing selected", "Select a requirement in the tree first.")
            return

        # Cascade: deleting a parent also removes every (possibly nested) child under it --
        # an orphaned sub-formula with a dangling parent_reqid would be meaningless downstream
        # (leaf_requirements(), the tree, everything assumes parent_reqid always resolves).
        to_delete = {req.reqid}
        changed = True
        while changed:
            changed = False
            for r in self.state.fret_import.requirements:
                if r.parent_reqid in to_delete and r.reqid not in to_delete:
                    to_delete.add(r.reqid)
                    changed = True

        if len(to_delete) > 1:
            message = f"Delete {req.reqid} and its {len(to_delete) - 1} sub-formula(s)?"
        else:
            message = f"Delete {req.reqid}?"
        message += "\n\nThis only affects the current session -- nothing is written to disk until you save or export again."

        confirm = QMessageBox.question(
            self, "Delete requirement", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.state.fret_import.requirements = [
            r for r in self.state.fret_import.requirements if r.reqid not in to_delete
        ]
        self.state.recommended_split_reqids -= to_delete

        if self.state.selected_requirement_id in to_delete:
            self.state.selected_requirement_id = None
            self.state.split_suggestion = None
            self.state.split_accepted = False
            self.state.sub_formulas = []
            self.state.validation = None
            self.suggestion_label.clear()
            self.force_split_button.setVisible(False)

        self._refresh_requirement_tree()

    def _on_requirement_selected(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        self.state.selected_requirement_id = current.data(0, Qt.ItemDataRole.UserRole)
        self.state.split_suggestion = None
        self.state.split_accepted = False
        self.state.sub_formulas = []
        self.suggestion_label.clear()
        self.force_split_button.setVisible(False)
        searched = self.state.search_results.get(self.state.selected_requirement_id)
        if searched is not None:
            self._show_suggestion(searched, source="LTLsplit search")
        self._refresh_formula_display()

    def _refresh_formula_display(self) -> None:
        req = None
        if self.state.fret_import and self.state.selected_requirement_id:
            req = self.state.fret_import.requirement(self.state.selected_requirement_id)
        if req is None:
            self.formula_label.setText("(select a requirement)")
            self.variables_label.clear()
            self.complexity_label.clear()
            self._refresh_sub_formula_list()
            return
        self.formula_label.setText(self._format_formulas(req.pt_formula, req.ft_formula, multiline=True))
        self.variables_label.setText(", ".join(req.variable_names) or "(none referenced)")
        self.complexity_label.setText("Complexity: " + self._complexity_text(req.pt_formula, req.ft_formula))
        self._refresh_sub_formula_list()

    def _declared_names(self) -> set[str] | None:
        if not self.state.fret_import:
            return None
        return {v.name for v in self.state.fret_import.variables}

    def _complexity_text(self, pt: str, ft: str) -> str:
        """e.g. "pt 12.5 (11 operators, 3 variables) | ft 12.5 (...)" -- only the forms that
        exist, since an .smv import fills just one of pt/ft."""
        declared = self._declared_names()
        parts = []
        for label, formula in (("pt", pt), ("ft", ft)):
            if formula:
                c = formula_complexity(formula, declared)
                parts.append(f"{label} {c.score:g} ({c.operators} operators, {c.variables} variables)")
        return " | ".join(parts) or "(no formula)"

    def _refresh_decomposition_complexity(self, req, sub_formulas) -> None:
        """Compares the original's complexity with the parts' -- the largest part is what a
        split actually buys (each monitor/check gets smaller), the sum shows the overhead."""
        if req is None or len(sub_formulas) < 2:
            self.decomposition_complexity_label.clear()
            return
        declared = self._declared_names()
        lines = []
        for label, original, parts in (
            ("pt", req.pt_formula, [s.pt_formula for s in sub_formulas]),
            ("ft", req.ft_formula, [s.ft_formula for s in sub_formulas]),
        ):
            if not original or not all(parts):
                continue
            scores = [formula_complexity(f, declared).score for f in parts]
            lines.append(
                f"{label}: original {formula_complexity(original, declared).score:g} -> parts "
                f"{', '.join(f'{x:g}' for x in scores)} (max {max(scores):g}, sum {sum(scores):g})"
            )
        self.decomposition_complexity_label.setText(
            "Decomposition complexity -- " + "; ".join(lines) if lines else ""
        )

    # -- ptLTL / ftLTL view -------------------------------------------------------------

    def _set_formula_view(self, view: str) -> None:
        """Switches the page between showing the past-time formula, the future-time formula,
        or both. Only the display changes -- every requirement keeps both formulas, and the
        LLM still sees both."""
        self.formula_view = view
        self._settings.setValue(_FORMULA_VIEW_SETTING, view)
        self.formula_view_buttons[view].setChecked(True)
        self._update_formula_heading()
        req = self._selected_requirement()
        if req is not None:
            self.formula_label.setText(self._format_formulas(req.pt_formula, req.ft_formula, multiline=True))
        self._refresh_sub_formula_list()

    def _update_formula_heading(self) -> None:
        self.formula_heading.setText({
            "pt": "Original formula (ptLTL, past-time):",
            "ft": "Original formula (ftLTL, future-time):",
        }.get(self.formula_view, "Original formula (past-time / future-time):"))

    def _format_formulas(self, pt: str, ft: str, multiline: bool = False) -> str:
        if self.formula_view == "pt":
            return pt
        if self.formula_view == "ft":
            return ft
        return f"pt: {pt}\nft: {ft}" if multiline else f"pt: {pt} | ft: {ft}"

    # -- split suggestion / decomposition ----------------------------------------------

    def _selected_requirement(self):
        if not self.state.fret_import or not self.state.selected_requirement_id:
            return None
        return self.state.fret_import.requirement(self.state.selected_requirement_id)

    def _on_suggest_clicked(self) -> None:
        req = self._selected_requirement()
        if req is None:
            QMessageBox.information(self, "No requirement selected", "Import a FRET file and select a requirement first.")
            return
        api_key = self.api_key_edit.text().strip()
        self.suggestion_label.setText("Asking the LLM for a split suggestion…")
        self._run_llm(
            lambda: suggest_split(req.pt_formula, req.ft_formula, api_key=api_key),
            lambda suggestion, exc: self._on_suggestion_ready(req, suggestion, exc),
        )

    def _run_llm(self, fn, on_done) -> None:
        """Runs an LLM call off the GUI thread (a blocking call there freezes the window and
        the desktop reports "not responding"). The split buttons and requirement tree are
        locked meanwhile so the reply can't land on a different requirement than it was asked
        about. `self._llm_thread` is non-None while a call is in flight."""
        def _done(result, exc) -> None:
            self._llm_thread = None
            on_done(result, exc)

        self._llm_thread = run_in_background(
            self, fn, _done,
            busy_widgets=(self.suggest_button, self.accept_button, self.reject_button,
                          self.force_split_button, self.requirement_tree),
        )

    def _on_suggestion_ready(self, req, suggestion, exc) -> None:
        if exc is not None:
            self.suggestion_label.clear()
            if isinstance(exc, MissingAPIKeyError):
                QMessageBox.information(self, "API key needed", str(exc))
            else:  # surface any Anthropic API/network failure
                QMessageBox.critical(self, "Suggestion failed", f"Couldn't get a split suggestion: {exc}")
            return
        if self.state.selected_requirement_id != req.reqid:
            return  # selection changed meanwhile -- stale answer
        self.state.search_results[req.reqid] = suggestion
        self._show_suggestion(suggestion)

    def _show_suggestion(self, suggestion, source: str = "") -> None:
        """Shows a verdict for the selected requirement and makes it the one Accept acts on."""
        self.state.split_suggestion = suggestion
        verdict = "Split recommended" if suggestion.should_split else "No split recommended"
        opportunity = suggestion.refactoring_opportunity.replace("_", " ")
        opportunity_text = f" [{opportunity}]" if opportunity and opportunity != "none" else ""
        prefix = f"{source}: " if source else ""
        self.suggestion_label.setText(
            f"{prefix}{verdict}{opportunity_text} (suggested {suggestion.suggested_count} part(s)): {suggestion.rationale}"
        )
        self.force_split_button.setVisible(not suggestion.should_split)

    # -- "LTLsplit search": asks the LLM about every requirement, one at a time -------------

    def _on_search_clicked(self) -> None:
        if not self.state.fret_import:
            QMessageBox.information(self, "Nothing to search", "Import a FRET file first.")
            return
        leaves = self.state.fret_import.leaf_requirements()
        # FRET exports requirements that were written but never formalized with empty
        # semantics -- nothing for the LLM to judge, so they're reported as skipped instead.
        self._search_skipped = [r.reqid for r in leaves if not (r.pt_formula or r.ft_formula)]
        searchable = [r for r in leaves if r.pt_formula or r.ft_formula]
        if not searchable:
            QMessageBox.information(
                self, "Nothing to search",
                "No requirement has a formula to check"
                + (f" ({len(self._search_skipped)} have no formula)." if self._search_skipped else "."),
            )
            return

        api_key = self.api_key_edit.text().strip()
        self._search_queue = list(searchable)
        self._search_total = len(self._search_queue)
        self._search_done: list[FretRequirement] = []
        set_status(self.search_status_label, None)
        self.search_status_label.setText(f"Searching {self._search_total} requirement(s)…")
        # Locked for the whole batch, not just one sub-call -- unlike _run_llm, which only
        # ever has one call in flight at a time, this chains many; without a self-managed lock
        # run_in_background would re-enable everything between each pair of calls.
        self._search_busy_widgets = (
            self.suggest_button, self.accept_button, self.reject_button, self.force_split_button,
            self.requirement_tree, self.search_button,
        )
        for widget in self._search_busy_widgets:
            widget.setEnabled(False)
        self._advance_search(api_key)

    def _advance_search(self, api_key: str) -> None:
        if not self._search_queue:
            for widget in self._search_busy_widgets:
                widget.setEnabled(True)
            self.search_button.setText("LTLsplit search")
            self._llm_thread = None  # lets _wait_for_llm-style polling see the whole batch as done
            self._report_search_summary()
            return
        req = self._search_queue.pop(0)
        done = self._search_total - len(self._search_queue)
        self.search_button.setText(f"Searching… ({done}/{self._search_total})")
        self._llm_thread = run_in_background(
            self,
            lambda: suggest_split(req.pt_formula, req.ft_formula, api_key=api_key),
            lambda suggestion, exc: self._on_search_result_ready(req, suggestion, exc, api_key),
        )

    def _on_search_result_ready(self, req: FretRequirement, suggestion, exc, api_key: str) -> None:
        if exc is not None:
            self._search_queue = []
            for widget in self._search_busy_widgets:
                widget.setEnabled(True)
            self.search_button.setText("LTLsplit search")
            self._llm_thread = None
            set_status(self.search_status_label, "danger")
            self.search_status_label.setText(
                f"Search stopped at {req.reqid.strip()} after {len(self._search_done)} of {self._search_total}."
            )
            if isinstance(exc, MissingAPIKeyError):
                QMessageBox.information(self, "API key needed", str(exc))
            else:  # surface any Anthropic API/network failure
                QMessageBox.critical(self, "Search stopped", f"Stopped after a failure on {req.reqid}: {exc}")
            return
        self.state.search_results[req.reqid] = suggestion
        self._search_done.append(req)
        if suggestion.should_split:
            self.state.recommended_split_reqids.add(req.reqid)
        else:
            self.state.recommended_split_reqids.discard(req.reqid)
        if self.state.selected_requirement_id == req.reqid:
            self._show_suggestion(suggestion, source="LTLsplit search")
        self._refresh_requirement_tree_highlights()
        self._advance_search(api_key)

    def _report_search_summary(self) -> None:
        """Always says how the search ended -- a run where the LLM recommends nothing would
        otherwise look exactly like one that never ran."""
        results = [(r, self.state.search_results[r.reqid]) for r in self._search_done]
        recommended = [r.reqid.strip() for r, s in results if s.should_split]
        reasons: dict[str, int] = {}
        for _r, s in results:
            if not s.should_split:
                key = (s.refactoring_opportunity or "none").replace("_", " ")
                reasons[key] = reasons.get(key, 0) + 1

        lines = [f"Checked {len(results)} requirement(s)."]
        if recommended:
            lines.append(f"Split recommended for {len(recommended)} (highlighted): {', '.join(recommended)}.")
        else:
            lines.append("No split recommended for any of them.")
        if reasons:
            lines.append("Kept whole: " + ", ".join(f"{n} {k}" for k, n in sorted(reasons.items())) + ".")
        if self._search_skipped:
            lines.append(
                f"Skipped {len(self._search_skipped)} with no formula: "
                + ", ".join(r.strip() for r in self._search_skipped) + "."
            )
        lines.append("Select a requirement to see the LLM's reasoning; Force Split is still available.")
        text = "\n".join(lines)
        set_status(self.search_status_label, "success" if recommended else "muted")
        self.search_status_label.setText(text)
        QMessageBox.information(self, "LTLsplit search finished", text)

    def _decompose_and_populate(self, count: int | None) -> None:
        req = self._selected_requirement()
        if req is None:
            QMessageBox.information(self, "No requirement selected", "Import a FRET file and select a requirement first.")
            return
        api_key = self.api_key_edit.text().strip()
        self._run_llm(
            lambda: decompose(req.reqid, req.pt_formula, req.ft_formula, count, api_key=api_key),
            lambda sub_formulas, exc: self._on_decomposition_ready(req, sub_formulas, exc),
        )

    def _on_decomposition_ready(self, req, sub_formulas, exc) -> None:
        if exc is not None:
            if isinstance(exc, MissingAPIKeyError):
                QMessageBox.information(self, "API key needed", str(exc))
            else:  # surface any Anthropic API/network failure
                QMessageBox.critical(self, "Decomposition failed", f"Couldn't decompose the formula: {exc}")
            return
        if self.state.selected_requirement_id != req.reqid:
            return  # selection changed meanwhile -- stale answer
        self.state.split_accepted = True
        self.state.sub_formulas = sub_formulas
        self.state.recommended_split_reqids.discard(req.reqid)  # decision made -- stop flagging it
        self._refresh_sub_formula_list()
        self._save_split(req, sub_formulas)

    def _save_split(self, parent, sub_formulas: list[SubFormula]) -> None:
        """Adds the split's sub-formulas to the session as requirements nested under `parent`
        and saves the session (see `_save_session`). A re-split replaces the parent's previous
        sub-formulas instead of piling a second set of the same ids next to them."""
        if self.state.fret_import is None or not self.state.fret_import_path:
            return  # nothing imported to save next to (and a scratch project has been saved by now)
        fret_import = self.state.fret_import
        previous = list(fret_import.requirements)
        superseded = self._descendants(parent.reqid)
        declared = self._declared_names() or set()
        fret_import.requirements = [r for r in previous if r.reqid not in superseded] + [
            FretRequirement(
                reqid=sub.id,
                fulltext=f"(LLM split of {parent.reqid}) {parent.fulltext}".strip(),
                pt_formula=sub.pt_formula,
                ft_formula=sub.ft_formula,
                variable_names=referenced_variable_names(sub.pt_formula, sub.ft_formula, declared),
                parent_reqid=parent.reqid,
                is_assumption=parent.is_assumption,
            )
            for sub in sub_formulas
        ]
        first_save = not self.state.session_export_path
        export_path = self._save_session(default_name=f"{parent.reqid}_split")
        if export_path is None:
            fret_import.requirements = previous
            return
        self._select_requirement_item(parent.reqid)
        if first_save:
            QMessageBox.information(
                self, "Split saved",
                f"Saved a copy with {len(sub_formulas)} new requirement(s) to:\n{export_path}\n\n"
                "The original file was not modified. This copy is now the active file -- "
                "any further splits, edits and additions this session are saved into it too, "
                "with no further prompt.",
            )

    def _descendants(self, reqid: str) -> set[str]:
        """Every requirement nested (at any depth) under `reqid`, not including itself."""
        found: set[str] = set()
        frontier = {reqid}
        while frontier:
            frontier = {
                r.reqid for r in self.state.fret_import.requirements
                if r.parent_reqid in frontier and r.reqid not in found
            }
            found |= frontier
        return found

    # -- saving the session -------------------------------------------------------------

    def _resolve_export_path(self, default_name: str) -> Path | None:
        """The session's save file. Only the first save of an import asks for a name (put next
        to the imported file, in ltlsplitter_exports/); later saves reuse it, so one sitting
        accumulates into one file. With nothing imported (a project started from scratch here)
        the user picks the location."""
        if self.state.session_export_path:
            return Path(self.state.session_export_path)
        if not self.state.fret_import_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save requirements", f"{default_name}.json", "FRET export (*.json)",
            )
            if not path:
                return None
            return Path(path if path.endswith(".json") else path + ".json")
        name, ok = QInputDialog.getText(
            self, "Save", "File name for the new copy (original file is never modified):", text=default_name,
        )
        if not ok or not name.strip():
            return None
        name = name.strip()
        if not name.endswith(".json"):
            name += ".json"
        return Path(self.state.fret_import_path).parent / _EXPORTS_DIR_NAME / name

    def _save_session(self, default_name: str | None = None) -> Path | None:
        """Writes the whole in-memory session -- edited requirements, splits, requirements and
        variables added here, deletions, assumption flags -- to the session's save file, then
        makes that file the active one. Returns the path, or None if nothing was saved."""
        if self.state.fret_import is None:
            QMessageBox.information(self, "Nothing to save", "Import a file or add a requirement first.")
            return None
        if default_name is None:
            default_name = f"{self.state.fret_import.project or 'requirements'}_edited"
        export_path = self._resolve_export_path(default_name)
        if export_path is None:
            return None
        try:
            save_session(self.state.fret_import, export_path, source_path=self.state.fret_import_path or None)
            new_import = import_fret_file(export_path)
        except Exception as exc:  # noqa: BLE001 -- surface any file-I/O or re-parse failure
            QMessageBox.critical(self, "Save failed", f"Couldn't save: {exc}")
            return None

        self.state.fret_import = new_import
        self.state.fret_import_path = str(export_path)
        self.state.session_export_path = str(export_path)
        set_status(self.save_status_label, "success")
        self.save_status_label.setText(f"Saved to {export_path}")
        self.import_label.setText(f"{new_import.project}: {len(new_import.requirements)} requirement(s)")
        self._refresh_requirement_tree()
        return export_path

    # -- writing / editing requirements and variables ------------------------------------

    def _ensure_project(self) -> FretImport:
        """Lets a project be started from scratch here, with nothing imported."""
        if self.state.fret_import is None:
            self.state.fret_import = FretImport(project="new_project")
            self.import_label.setText("new_project: 0 requirement(s)")
        return self.state.fret_import

    def _style_examples(self) -> list[FretRequirement]:
        """A few of the file's own requirements, so the LLM matches the project's notation."""
        if not self.state.fret_import:
            return []
        candidates = [
            r for r in self.state.fret_import.requirements
            if not r.parent_reqid and r.fulltext and r.pt_formula and r.ft_formula
        ]
        return candidates[:_STYLE_EXAMPLE_COUNT]

    def _unused_reqid(self) -> str:
        existing = {r.reqid for r in self.state.fret_import.requirements} if self.state.fret_import else set()
        n = len(existing) + 1
        while f"req_{n}" in existing:
            n += 1
        return f"req_{n}"

    def _requirement_dialog(self, requirement: FretRequirement | None) -> RequirementDialog:
        fret_import = self.state.fret_import
        child_count = len(self._descendants(requirement.reqid)) if requirement is not None else 0
        return RequirementDialog(
            variables=list(fret_import.variables) if fret_import else [],
            existing_reqids={r.reqid for r in fret_import.requirements} if fret_import else set(),
            api_key=self.api_key_edit.text().strip(),
            requirement=requirement,
            examples=self._style_examples(),
            child_count=child_count,
            default_reqid=self._unused_reqid(),
            on_add_variable=self._add_variable,
            parent=self,
        )

    def _on_new_requirement_clicked(self) -> None:
        dialog = self._requirement_dialog(None)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        fret_import = self._ensure_project()
        req = FretRequirement(
            reqid=dialog.reqid(),
            fulltext=dialog.fulltext(),
            pt_formula=dialog.pt_formula(),
            ft_formula=dialog.ft_formula(),
            variable_names=referenced_variable_names(dialog.pt_formula(), dialog.ft_formula(), self._declared_names() or set()),
        )
        fret_import.requirements.append(req)
        self.state.selected_requirement_id = req.reqid
        if self._save_session(default_name=f"{fret_import.project or 'requirements'}_edited") is None:
            self._refresh_requirement_tree()  # kept in the session, just not on disk yet

    def _on_edit_requirement_clicked(self) -> None:
        req = self._selected_requirement()
        if req is None:
            QMessageBox.information(self, "Nothing selected", "Select a requirement in the tree first.")
            return
        dialog = self._requirement_dialog(req)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        req = self._selected_requirement()  # the dialog's Add Variable may have re-saved/reloaded
        if req is None:
            return
        formulas_changed = (req.pt_formula, req.ft_formula) != (dialog.pt_formula(), dialog.ft_formula())
        req.fulltext = dialog.fulltext()
        req.pt_formula = dialog.pt_formula()
        req.ft_formula = dialog.ft_formula()
        req.variable_names = referenced_variable_names(req.pt_formula, req.ft_formula, self._declared_names() or set())
        if formulas_changed:
            # Any earlier suggestion/validation was about the old formula.
            self.state.search_results.pop(req.reqid, None)
            self.state.recommended_split_reqids.discard(req.reqid)
            self.state.split_suggestion = None
            self.state.validation = None
            self.suggestion_label.clear()
            self.force_split_button.setVisible(False)
        if self._save_session() is None:
            self._refresh_formula_display()

    def _add_variable(self, suggested_name: str = "") -> Variable | None:
        """Shows the Add Variable pop-up; on Add, declares the variable and saves the session.
        Returns the new variable (also used by the requirement dialog's own Add Variable)."""
        fret_import = self.state.fret_import
        dialog = VariableDialog(
            existing_names={v.name for v in fret_import.variables} if fret_import else set(),
            suggested_name=suggested_name,
            formulas=self._all_formulas(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        var = dialog.variable()
        fret_import = self._ensure_project()
        fret_import.variables.append(var)
        # Requirements that already used this name (flagged "possibly undeclared" until now)
        # reference it from here on.
        for req in fret_import.requirements:
            if var.name not in req.variable_names and var.name in referenced_variable_names(req.pt_formula, req.ft_formula, {var.name}):
                req.variable_names.append(var.name)
        if self._save_session() is None:
            self._refresh_formula_display()
        return var

    def _all_formulas(self) -> list[str]:
        if not self.state.fret_import:
            return []
        return [f for r in self.state.fret_import.requirements for f in (r.pt_formula, r.ft_formula) if f]

    def _edit_variable(self, name: str) -> bool:
        """Shows the variable pop-up filled in with `name`'s current values; on Save, replaces
        it in place (keeping its position) and saves the session. Returns whether it changed."""
        fret_import = self.state.fret_import
        index = next((i for i, v in enumerate(fret_import.variables) if v.name == name), None) if fret_import else None
        if index is None:
            return False
        dialog = VariableDialog(
            existing_names={v.name for v in fret_import.variables},
            variable=fret_import.variables[index],
            formulas=self._all_formulas(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        updated = dialog.variable()
        if not fret_import.variables[index].topic and updated.topic == f"/{name}":
            updated.topic = ""  # the default, still unset -- not an edit
        if updated == fret_import.variables[index]:
            return False
        fret_import.variables[index] = updated
        # Anything validated with the old type/range is stale now.
        self.state.validation = None
        self.state.realizability_results = {}
        if self._save_session() is None:
            self._refresh_formula_display()
        return True

    def _on_variable_table_clicked(self) -> None:
        dialog = VariableTableDialog(
            get_variables=lambda: list(self.state.fret_import.variables) if self.state.fret_import else [],
            get_requirements=lambda: list(self.state.fret_import.requirements) if self.state.fret_import else [],
            on_add=self._add_variable,
            on_edit=self._edit_variable,
            parent=self,
        )
        dialog.exec()

    def _on_accept_clicked(self) -> None:
        suggestion = self.state.split_suggestion
        if suggestion is None:
            QMessageBox.information(self, "No suggestion yet", "Click 'Suggest Split' first.")
            return
        self._decompose_and_populate(suggestion.suggested_count)

    def _on_force_split_clicked(self) -> None:
        self._decompose_and_populate(None)

    def _on_reject_clicked(self) -> None:
        req = self._selected_requirement()
        self.state.split_accepted = False
        self.state.sub_formulas = []
        if req is not None:
            self.state.recommended_split_reqids.discard(req.reqid)  # decision made -- stop flagging it
            self._refresh_requirement_tree_highlights()
        self._refresh_sub_formula_list()

    def _refresh_sub_formula_list(self) -> None:
        self.sub_formula_list.blockSignals(True)
        self.sub_formula_list.clear()
        for sub in self.state.active_sub_formulas():
            item = QListWidgetItem(f"{sub.id} | {self._format_formulas(sub.pt_formula, sub.ft_formula)}")
            item.setToolTip(
                f"pt: {sub.pt_formula}\nft: {sub.ft_formula}\n"
                f"Complexity: {self._complexity_text(sub.pt_formula, sub.ft_formula)}"
            )
            item.setData(Qt.ItemDataRole.UserRole, sub.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.sub_formula_list.addItem(item)
        self.sub_formula_list.blockSignals(False)
        self._refresh_reference_check()
        self._refresh_decomposition_complexity(self._selected_requirement(), self.state.active_sub_formulas())

    def _on_sub_formula_edited(self, item: QListWidgetItem) -> None:
        """Lets the user hand-correct a sub-formula in place. The text is "id | <formula>" when
        only ptLTL or ftLTL is shown (only that formula is updated, the hidden one is kept), or
        "id | pt: ... | ft: ..." when both are. The id is split off at the first " | " only, so
        formulas may themselves contain "|" (FRET's disjunction)."""
        sub_id = item.data(Qt.ItemDataRole.UserRole)
        _id_part, sep, rest = item.text().partition(" | ")
        if not sep:
            return
        for i, sub in enumerate(self.state.sub_formulas):
            if sub.id != sub_id:
                continue
            pt_formula, ft_formula = sub.pt_formula, sub.ft_formula
            if self.formula_view == "pt":
                pt_formula = rest.strip().removeprefix("pt:").strip()
            elif self.formula_view == "ft":
                ft_formula = rest.strip().removeprefix("ft:").strip()
            else:
                pt_part, sep, ft_part = rest.partition(" | ft:")
                if not sep:
                    return
                pt_formula = pt_part.strip().removeprefix("pt:").strip()
                ft_formula = ft_part.strip()
            self.state.sub_formulas[i] = SubFormula(id=sub_id, pt_formula=pt_formula, ft_formula=ft_formula)
            self.sub_formula_list.blockSignals(True)  # setToolTip would re-emit itemChanged
            item.setToolTip(
                f"pt: {pt_formula}\nft: {ft_formula}\n"
                f"Complexity: {self._complexity_text(pt_formula, ft_formula)}"
            )
            self.sub_formula_list.blockSignals(False)
            break
        self._refresh_reference_check()
        self._refresh_decomposition_complexity(self._selected_requirement(), self.state.active_sub_formulas())

    def _refresh_reference_check(self) -> None:
        if not self.state.fret_import:
            self.reference_label.clear()
            return
        declared = {v.name for v in self.state.fret_import.variables}
        undeclared: list[str] = []
        for sub in self.state.active_sub_formulas():
            for name in find_undeclared_references(sub.pt_formula + " " + sub.ft_formula, declared):
                if name not in undeclared:
                    undeclared.append(name)
        if undeclared:
            set_status(self.reference_label, "danger")
            self.reference_label.setText("Possibly undeclared: " + ", ".join(undeclared))
        else:
            set_status(self.reference_label, "success")
            self.reference_label.setText("All referenced identifiers are declared variables.")
