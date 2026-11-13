from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ltlsplitter.core.fret_import import InvalidFretFileError, append_sub_formulas_and_save, import_fret_file
from ltlsplitter.core.llm_decompose import MissingAPIKeyError, decompose, suggest_split
from ltlsplitter.core.models import SubFormula
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.core.reference_check import find_undeclared_references
from ltlsplitter.gui.pages.base import WizardPage
from ltlsplitter.gui.theme import compact, set_status
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


class ImportSplitPage(WizardPage):
    title = "1. Import & Split Review"
    description = (
        "Import a FRET project export, pick one requirement from it, and let an LLM suggest "
        "whether it should be split into independent sub-properties. Review and accept/reject "
        "the suggestion, then have the LLM perform the split -- the sub-formulas are editable "
        "before moving on to validation. Accepting a split saves it as a new copy of the FRET "
        "file (the original is never modified) with the sub-formulas appended as requirements "
        "nested under the original, shown here as a dropdown. The Assumption checkbox marks a "
        "requirement as an environment constraint rather than a system guarantee (seeded from "
        "FRET's \"*_assumption\" naming convention, correct it if wrong) -- used by the "
        "realizability check on page 3."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)
        self._llm_thread = None
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
        import_button = QPushButton("Import FRET file...")
        import_button.clicked.connect(self._on_import_clicked)
        self.import_label = QLabel("(no file imported)")
        import_row.addWidget(import_button)
        import_row.addWidget(self.import_label, 1)
        self.content_layout.addLayout(import_row)

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
        assumption_actions_row.addWidget(select_all_button)
        assumption_actions_row.addWidget(clear_all_button)
        assumption_actions_row.addWidget(delete_button)
        assumption_actions_row.addStretch()
        left.addLayout(assumption_actions_row)

        self.requirement_tree = QTreeWidget()
        self.requirement_tree.setColumnCount(2)
        self.requirement_tree.setHeaderLabels(["Requirement", "Assumption"])
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
        self.force_split_button = compact(QPushButton("Force split anyway (ask LLM for 2 parts)"))
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
        path, _ = QFileDialog.getOpenFileName(self, "Import FRET project export", "", "JSON files (*.json)")
        if not path:
            return
        try:
            fret_import = import_fret_file(path)
        except InvalidFretFileError as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.state.fret_import = fret_import
        self.state.fret_import_path = path
        self.state.session_export_path = ""
        self.state.selected_requirement_id = None
        self.state.split_suggestion = None
        self.state.split_accepted = False
        self.state.sub_formulas = []
        self.force_split_button.setVisible(False)
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
        self._refresh_formula_display()

    def _refresh_formula_display(self) -> None:
        req = None
        if self.state.fret_import and self.state.selected_requirement_id:
            req = self.state.fret_import.requirement(self.state.selected_requirement_id)
        if req is None:
            self.formula_label.setText("(select a requirement)")
            self.variables_label.clear()
            self._refresh_sub_formula_list()
            return
        self.formula_label.setText(self._format_formulas(req.pt_formula, req.ft_formula, multiline=True))
        self.variables_label.setText(", ".join(req.variable_names) or "(none referenced)")
        self._refresh_sub_formula_list()

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
        self.state.split_suggestion = suggestion
        verdict = "Split recommended" if suggestion.should_split else "No split recommended"
        self.suggestion_label.setText(
            f"{verdict} (suggested {suggestion.suggested_count} part(s)): {suggestion.rationale}"
        )
        self.force_split_button.setVisible(not suggestion.should_split)

    def _decompose_and_populate(self, count: int) -> None:
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
        self._refresh_sub_formula_list()
        self._save_split(req, sub_formulas)

    def _save_split(self, parent, sub_formulas: list[SubFormula]) -> None:
        """Saves the split as a new copy of the FRET file (original untouched), with the
        sub-formulas appended as requirements nested under `parent`, then makes that copy the
        active file going forward so later stages (and future splits) see them as real
        requirements -- not just in-memory for this one session.

        Only the FIRST split of a given import prompts for a file name -- every later split in
        the same session (tracked via `state.session_export_path`, reset on a fresh import)
        reuses that same file instead, so splitting several requirements in one sitting
        accumulates into one file rather than prompting -- and nesting a fresh
        "ltlsplitter_exports" directory inside the previous one -- every single time."""
        if not self.state.fret_import_path:
            return  # nothing to copy from (shouldn't normally happen -- a split needs an import)

        if self.state.session_export_path:
            export_path = Path(self.state.session_export_path)
        else:
            default_name = f"{parent.reqid}_split"
            name, ok = QInputDialog.getText(
                self, "Save split", "File name for the new copy (original file is never modified):", text=default_name,
            )
            if not ok or not name.strip():
                return
            name = name.strip()
            if not name.endswith(".json"):
                name += ".json"
            export_dir = Path(self.state.fret_import_path).parent / _EXPORTS_DIR_NAME
            export_path = export_dir / name

        declared_names = {v.name for v in self.state.fret_import.variables}
        try:
            append_sub_formulas_and_save(
                self.state.fret_import_path, sub_formulas, parent, self.state.fret_import.project,
                declared_names, export_path, current_requirements=self.state.fret_import.requirements,
            )
            new_import = import_fret_file(export_path)
        except Exception as exc:  # noqa: BLE001 -- surface any file-I/O or re-parse failure
            QMessageBox.critical(self, "Save failed", f"Couldn't save the split: {exc}")
            return

        self.state.fret_import = new_import
        self.state.fret_import_path = str(export_path)
        self.state.session_export_path = str(export_path)
        self._refresh_requirement_tree()
        self._select_requirement_item(parent.reqid)
        QMessageBox.information(
            self, "Split saved",
            f"Saved a copy with {len(sub_formulas)} new requirement(s) to:\n{export_path}\n\n"
            "The original FRET file was not modified. This copy is now the active file -- "
            "any further splits this session are appended into it too, with no further prompt.",
        )

    def _on_accept_clicked(self) -> None:
        suggestion = self.state.split_suggestion
        if suggestion is None:
            QMessageBox.information(self, "No suggestion yet", "Click 'Suggest Split' first.")
            return
        self._decompose_and_populate(suggestion.suggested_count)

    def _on_force_split_clicked(self) -> None:
        self._decompose_and_populate(2)

    def _on_reject_clicked(self) -> None:
        self.state.split_accepted = False
        self.state.sub_formulas = []
        self._refresh_sub_formula_list()

    def _refresh_sub_formula_list(self) -> None:
        self.sub_formula_list.blockSignals(True)
        self.sub_formula_list.clear()
        for sub in self.state.active_sub_formulas():
            item = QListWidgetItem(f"{sub.id} | {self._format_formulas(sub.pt_formula, sub.ft_formula)}")
            item.setToolTip(f"pt: {sub.pt_formula}\nft: {sub.ft_formula}")
            item.setData(Qt.ItemDataRole.UserRole, sub.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.sub_formula_list.addItem(item)
        self.sub_formula_list.blockSignals(False)
        self._refresh_reference_check()

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
            item.setToolTip(f"pt: {pt_formula}\nft: {ft_formula}")
            self.sub_formula_list.blockSignals(False)
            break
        self._refresh_reference_check()

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
