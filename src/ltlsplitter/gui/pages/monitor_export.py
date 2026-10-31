from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from ltlsplitter.core.models import FretRequirement, Specification, Variable, VariableRole
from ltlsplitter.core.monitor_grouping import suggest_groups
from ltlsplitter.core.ogma import ToolNotFoundError, generate_ros2_monitor
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.base import WizardPage
from ltlsplitter.gui.theme import compact, set_status

_UNGROUPED = "Ungrouped"


def _sanitize_dirname(name: str) -> str:
    """Multiple groups can now be exported from the same chosen output directory -- each needs
    its own subdirectory underneath it, or a second export would silently overwrite the first
    (generate_ros2_monitor writes copilot/, Dockerfile, etc. directly into whatever directory
    it's given)."""
    sanitized = "".join(c if c.isalnum() else "_" for c in name).strip("_")
    return sanitized or "group"


class MonitorExportPage(WizardPage):
    title = "4. Ogma/Copilot Export"
    description = (
        "Ogma/Copilot only understands past-time LTL (H/O/S/Y) -- every property exported here "
        "is built from each requirement's pt form, never its ft form; there's no future-time "
        "support to fall back on. Organize the current system's requirements into monitoring "
        "groups -- each one becomes its own separate ROS2 Copilot monitor package, so a large "
        "system doesn't have to ship as a single monolithic monitor. \"Auto-suggest Groups\" "
        "clusters requirements that share a variable (they'd subscribe to the same topic "
        "anyway); drag requirements between groups, rename or add/remove groups by hand "
        "afterward. This produces a source package, not a running monitor -- see README.md's "
        "\"Using the generated monitor\" section for the compile/build/run steps (runhaskell, "
        "colcon build) and how to read violations off the generated handler topics."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)
        self._output_dir: Path | None = None
        self._tree_built_for_reqids: frozenset[str] | None = None
        self._topics_built_for_names: frozenset[str] | None = None

        self.content_layout.addWidget(QLabel("Source file:"))
        self.source_file_label = QLabel()
        self.source_file_label.setWordWrap(True)
        self.content_layout.addWidget(self.source_file_label)

        topics_label = QLabel(
            "Variable subscriptions (ROS topics the generated monitor subscribes to for each "
            "variable's live value -- double-click Topic to edit; defaults to /<variable name>):"
        )
        topics_label.setWordWrap(True)
        self.content_layout.addWidget(topics_label)
        self.topics_tree = QTreeWidget()
        self.topics_tree.setHeaderLabels(["Variable", "Topic"])
        self.topics_tree.setRootIsDecorated(False)
        self.topics_tree.setMinimumHeight(120)
        self.topics_tree.itemChanged.connect(self._on_topic_item_changed)
        self.content_layout.addWidget(self.topics_tree)

        self.content_layout.addWidget(QLabel("Monitoring groups (drag requirements between groups):"))

        group_actions_row = QHBoxLayout()
        auto_suggest_button = compact(QPushButton("Auto-suggest Groups"))
        auto_suggest_button.setToolTip("Clusters requirements that share a variable into the same group.")
        auto_suggest_button.clicked.connect(self._on_auto_suggest_clicked)
        add_group_button = compact(QPushButton("Add Group"))
        add_group_button.clicked.connect(self._on_add_group_clicked)
        remove_group_button = compact(QPushButton("Remove Selected Group"))
        remove_group_button.clicked.connect(self._on_remove_group_clicked)
        group_actions_row.addWidget(auto_suggest_button)
        group_actions_row.addWidget(add_group_button)
        group_actions_row.addWidget(remove_group_button)
        group_actions_row.addStretch()
        self.content_layout.addLayout(group_actions_row)

        self.group_tree = QTreeWidget()
        self.group_tree.setHeaderHidden(True)
        self.group_tree.setMinimumHeight(220)
        self.group_tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.group_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.group_tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.group_tree.itemChanged.connect(self._on_group_tree_item_changed)
        self.content_layout.addWidget(self.group_tree)

        export_group_row = QHBoxLayout()
        export_group_row.addWidget(QLabel("Export group:"))
        self.export_group_combo = QComboBox()
        export_group_row.addWidget(self.export_group_combo, 1)
        self.content_layout.addLayout(export_group_row)

        self.content_layout.addWidget(QLabel("Output directory:"))
        dir_row = QHBoxLayout()
        self.output_dir_label = QLabel("(none selected)")
        self.output_dir_label.setWordWrap(True)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_clicked)
        dir_row.addWidget(self.output_dir_label, 1)
        dir_row.addWidget(browse_button)
        self.content_layout.addLayout(dir_row)

        generate_button = compact(QPushButton("Generate Monitor for Selected Group"))
        generate_button.clicked.connect(self._on_generate_clicked)
        self.content_layout.addWidget(generate_button)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.content_layout.addWidget(self.status_label)

        self.content_layout.addStretch()

    # -- tree construction / grouping -----------------------------------------------------

    def on_show(self) -> None:
        self._render_source_file()
        current_reqids = frozenset(r.reqid for r in self._leaf_requirements())
        if current_reqids != self._tree_built_for_reqids:
            self._rebuild_tree_everything_ungrouped()
        current_variable_names = frozenset(v.name for v in self._exportable_variables())
        if current_variable_names != self._topics_built_for_names:
            self._rebuild_topics_tree()
        if self.state.generated_monitor_path:
            set_status(self.status_label, "success")
            self.status_label.setText(f"Last generated monitor: {self.state.generated_monitor_path}")

    def _leaf_requirements(self) -> list[FretRequirement]:
        if not self.state.fret_import:
            return []
        return self.state.fret_import.leaf_requirements()

    def _exportable_variables(self) -> list[Variable]:
        """Every variable the generated monitor could subscribe to -- Internal variables are
        derived at runtime from their `assignment` expression (see ogma.py's
        `_build_variable_db`), never observed on a topic directly, so they're excluded here too."""
        if not self.state.fret_import:
            return []
        return [v for v in self.state.fret_import.variables if v.role != VariableRole.INTERNAL]

    def _rebuild_topics_tree(self) -> None:
        """Rebuilt only when the exportable variable set actually changes (a fresh import, or a
        split that introduces/removes variables) -- revisiting this page otherwise must not
        discard topic overrides the user already typed in, the same rule `on_show` already
        follows for the group tree."""
        variables = self._exportable_variables()
        self.topics_tree.blockSignals(True)
        self.topics_tree.clear()
        for var in variables:
            if not var.topic:
                var.topic = f"/{var.name}"  # seed the editable default in place
            item = QTreeWidgetItem([var.name, var.topic])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
            item.setData(0, Qt.ItemDataRole.UserRole, var)
            self.topics_tree.addTopLevelItem(item)
        self.topics_tree.blockSignals(False)
        self._topics_built_for_names = frozenset(v.name for v in variables)

    def _on_topic_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 1:  # the Variable column (0) is shown, not meant to be renamed here
            return
        var = item.data(0, Qt.ItemDataRole.UserRole)
        if var is None:
            return
        var.topic = item.text(1).strip() or f"/{var.name}"
        item.setText(1, var.topic)

    def _render_source_file(self) -> None:
        """Shows the active FRET file -- `state.fret_import_path`, the same field `_save_split`
        (import_split.py) repoints at a split's saved copy, so this always reflects whichever
        file page 1's choices actually produced, not just the originally-imported one."""
        if not self.state.fret_import_path:
            self.source_file_label.setText("(no file imported -- import a FRET file on page 1 first)")
            return
        leaves = self._leaf_requirements()
        self.source_file_label.setText(
            f"{self.state.fret_import_path}\n{len(leaves)} requirement(s) available to group below"
        )

    @staticmethod
    def _requirement_item(reqid: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([reqid])
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
        return item

    @staticmethod
    def _group_header_item(name: str, *, editable: bool) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        return item

    def _rebuild_tree_everything_ungrouped(self) -> None:
        """The starting point whenever the current leaf-requirement set changes (a fresh
        import, or a split just got saved) -- nothing grouped yet, no requirement silently
        dropped. Replaces whatever grouping was there before, since it was built for a
        different set of requirements."""
        leaves = self._leaf_requirements()
        self.group_tree.blockSignals(True)
        self.group_tree.clear()
        ungrouped = self._group_header_item(_UNGROUPED, editable=False)
        self.group_tree.addTopLevelItem(ungrouped)
        for req in leaves:
            ungrouped.addChild(self._requirement_item(req.reqid))
        self.group_tree.expandAll()
        self.group_tree.blockSignals(False)
        self._tree_built_for_reqids = frozenset(r.reqid for r in leaves)
        self._refresh_export_group_selector()

    def _on_auto_suggest_clicked(self) -> None:
        leaves = self._leaf_requirements()
        if not leaves:
            QMessageBox.information(self, "Nothing to group", "Import a FRET file on page 1 first.")
            return

        groups = suggest_groups(leaves)
        self.group_tree.blockSignals(True)
        self.group_tree.clear()
        ungrouped = self._group_header_item(_UNGROUPED, editable=False)
        self.group_tree.addTopLevelItem(ungrouped)
        for group in groups:
            group_item = self._group_header_item(group.name, editable=True)
            self.group_tree.addTopLevelItem(group_item)
            for reqid in group.requirement_ids:
                group_item.addChild(self._requirement_item(reqid))
        self.group_tree.expandAll()
        self.group_tree.blockSignals(False)
        self._tree_built_for_reqids = frozenset(r.reqid for r in leaves)
        self._refresh_export_group_selector()

    def _on_add_group_clicked(self) -> None:
        existing_group_count = max(self.group_tree.topLevelItemCount() - 1, 0)  # minus Ungrouped
        name, ok = QInputDialog.getText(
            self, "Add group", "Group name:", text=f"Group {existing_group_count + 1}",
        )
        if not ok or not name.strip():
            return
        self.group_tree.addTopLevelItem(self._group_header_item(name.strip(), editable=True))
        self._refresh_export_group_selector()

    def _on_remove_group_clicked(self) -> None:
        item = self.group_tree.currentItem()
        if item is None or item.parent() is not None:
            QMessageBox.information(self, "No group selected", "Select a group (not a requirement) to remove.")
            return
        if item.text(0) == _UNGROUPED:
            QMessageBox.information(
                self, "Can't remove this", f'"{_UNGROUPED}" is a holding pen, not a deployable group.',
            )
            return

        ungrouped = self.group_tree.topLevelItem(0)
        for child in item.takeChildren():
            ungrouped.addChild(child)
        self.group_tree.takeTopLevelItem(self.group_tree.indexOfTopLevelItem(item))
        self._refresh_export_group_selector()

    def _on_group_tree_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.parent() is None:  # a group was renamed -- the export selector must follow
            self._refresh_export_group_selector()

    def _refresh_export_group_selector(self) -> None:
        current_name = self.export_group_combo.currentText()
        names = []
        for i in range(self.group_tree.topLevelItemCount()):
            item = self.group_tree.topLevelItem(i)
            if item.text(0) != _UNGROUPED:
                names.append(item.text(0))

        self.export_group_combo.blockSignals(True)
        self.export_group_combo.clear()
        self.export_group_combo.addItems(names)
        if current_name in names:
            self.export_group_combo.setCurrentText(current_name)
        self.export_group_combo.blockSignals(False)

    def _group_member_reqids(self, group_name: str) -> list[str]:
        for i in range(self.group_tree.topLevelItemCount()):
            item = self.group_tree.topLevelItem(i)
            if item.text(0) == group_name:
                return [item.child(j).text(0) for j in range(item.childCount())]
        return []

    # -- export -----------------------------------------------------------------------------

    def _on_browse_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select output directory")
        if directory:
            self._output_dir = Path(directory)
            self.output_dir_label.setText(directory)

    def _on_generate_clicked(self) -> None:
        if not self.state.fret_import:
            QMessageBox.information(self, "Nothing to export", "Import a FRET file on page 1 first.")
            return
        group_name = self.export_group_combo.currentText()
        if not group_name:
            QMessageBox.information(self, "No group to export", "Create at least one group above, then select it here.")
            return
        reqids = self._group_member_reqids(group_name)
        if not reqids:
            QMessageBox.information(self, "Empty group", f'"{group_name}" has no requirements in it -- drag some in first.')
            return
        if self._output_dir is None:
            QMessageBox.information(self, "No output directory", "Choose an output directory first.")
            return

        specs = []
        for reqid in reqids:
            req = self.state.fret_import.requirement(reqid)
            if req is not None:
                specs.append(Specification(requirement_id=req.reqid, ltl_formula=req.pt_formula))
        variables = self.state.fret_import.variables

        # Each group gets its own subdirectory under the chosen output directory -- reusing the
        # same directory for a second group would silently overwrite the first group's package.
        target_dir = self._output_dir / _sanitize_dirname(group_name)
        try:
            package_dir = generate_ros2_monitor(specs, target_dir, variables)
        except ToolNotFoundError as exc:
            set_status(self.status_label, "muted")
            self.status_label.setText(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- surface any ogma subprocess failure to the user
            set_status(self.status_label, "danger")
            self.status_label.setText(f"Generation failed: {exc}")
            return

        self.state.generated_monitor_path = str(package_dir)
        set_status(self.status_label, "success")
        self.status_label.setText(
            f'Generated monitor package for "{group_name}" at {package_dir}\n\n'
            "Next: compile the Copilot spec (runhaskell copilot/src/Copilot.hs), then colcon "
            "build -- see README.md's \"Using the generated monitor\" section for the full steps."
        )
