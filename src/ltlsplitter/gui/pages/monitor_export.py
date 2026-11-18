from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolTip,
    QTreeWidget,
    QTreeWidgetItem,
)

from ltlsplitter.core.models import FretRequirement, Specification, Variable, VariableRole
from ltlsplitter.core.monitor_grouping import auto_sort_requirements
from ltlsplitter.core.ogma import ToolNotFoundError, generate_ros2_monitor
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.base import WizardPage
from ltlsplitter.gui.theme import compact, set_status

_UNASSIGNED_VARIABLES = "Unassigned Variables"
_UNASSIGNED_REQUIREMENTS = "Unassigned Requirements"
_GROUP_ID_ROLE = Qt.ItemDataRole.UserRole


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
        "support to fall back on. Group the variables first -- drag them from \"Unassigned "
        "Variables\" into groups of your own -- then click \"Auto Sort\" to sort requirements "
        "into whichever group covers all of their variables; a requirement whose variables span "
        "more than one group is left in \"Unassigned Requirements\" for you to place by hand. "
        "Click a requirement to see just the variables it references. Each group becomes its "
        "own separate ROS2 Copilot monitor package, so a large system doesn't have to ship as "
        "one monolithic monitor. This produces a source package, not a running monitor -- see "
        "README.md's \"Using the generated monitor\" section for the compile/build/run steps "
        "(runhaskell, colcon build) and how to read violations off the generated handler topics."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)
        self._output_dir: Path | None = None
        self._variable_set_built_for: frozenset[str] | None = None
        self._requirement_tree_built_for_reqids: frozenset[str] | None = None
        self._next_group_id = 1

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

        self.content_layout.addWidget(QLabel("Variable groups (drag variables between groups):"))
        variable_actions_row = QHBoxLayout()
        add_variable_group_button = compact(QPushButton("Add Group"))
        add_variable_group_button.clicked.connect(self._on_add_group_clicked)
        remove_variable_group_button = compact(QPushButton("Remove Selected Group"))
        remove_variable_group_button.clicked.connect(self._on_remove_group_clicked)
        variable_actions_row.addWidget(add_variable_group_button)
        variable_actions_row.addWidget(remove_variable_group_button)
        variable_actions_row.addStretch()
        self.content_layout.addLayout(variable_actions_row)

        self.variable_tree = QTreeWidget()
        self.variable_tree.setHeaderHidden(True)
        self.variable_tree.setMinimumHeight(160)
        self.variable_tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.variable_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.variable_tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.variable_tree.itemChanged.connect(self._on_variable_group_renamed)
        self.content_layout.addWidget(self.variable_tree)

        auto_sort_row = QHBoxLayout()
        auto_sort_button = compact(QPushButton("Auto Sort"))
        auto_sort_button.setToolTip(
            "Sorts requirements into whichever variable group above covers all of their "
            "variables; a requirement spanning more than one group is left unassigned."
        )
        auto_sort_button.clicked.connect(self._on_auto_sort_clicked)
        auto_sort_row.addWidget(auto_sort_button)
        auto_sort_row.addStretch()
        self.content_layout.addLayout(auto_sort_row)

        self.content_layout.addWidget(QLabel("Requirements (drag between groups; click one to see its variables):"))
        self.requirement_tree = QTreeWidget()
        self.requirement_tree.setHeaderHidden(True)
        self.requirement_tree.setMinimumHeight(220)
        self.requirement_tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.requirement_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.requirement_tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.requirement_tree.itemClicked.connect(self._on_requirement_item_clicked)
        self.content_layout.addWidget(self.requirement_tree)

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
        current_variable_names = frozenset(v.name for v in self._exportable_variables())
        if current_variable_names != self._variable_set_built_for:
            self._rebuild_topics_tree()
            self._rebuild_variable_tree_everything_unassigned()
            self._variable_set_built_for = current_variable_names
        current_reqids = frozenset(r.reqid for r in self._leaf_requirements())
        if current_reqids != self._requirement_tree_built_for_reqids:
            self._rebuild_requirement_tree_everything_unassigned()
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
        `_build_variable_db`), never observed on a topic directly, so they're excluded here too
        -- which also means an internal variable never appears in any variable group, so
        `auto_sort_requirements` naturally treats it like any other not-yet-grouped variable."""
        if not self.state.fret_import:
            return []
        return [v for v in self.state.fret_import.variables if v.role != VariableRole.INTERNAL]

    def _rebuild_topics_tree(self) -> None:
        """Rebuilt only when the exportable variable set actually changes (a fresh import, or a
        split that introduces/removes variables) -- revisiting this page otherwise must not
        discard topic overrides the user already typed in, the same rule `on_show` already
        follows for the group trees below."""
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
    def _leaf_item(text: str) -> QTreeWidgetItem:
        """A draggable, non-editable, non-drop-target leaf -- a variable name in `variable_tree`
        or a reqid in `requirement_tree`."""
        item = QTreeWidgetItem([text])
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
        return item

    @staticmethod
    def _header_item(name: str, *, editable: bool, group_id: int | None = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)
        if group_id is not None:
            item.setData(0, _GROUP_ID_ROLE, group_id)
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        return item

    def _rebuild_variable_tree_everything_unassigned(self) -> None:
        """The starting point whenever the exportable variable set changes -- nothing grouped
        yet, built fresh for a different variable set than whatever grouping existed before."""
        self.variable_tree.blockSignals(True)
        self.variable_tree.clear()
        pool = self._header_item(_UNASSIGNED_VARIABLES, editable=False)
        self.variable_tree.addTopLevelItem(pool)
        for var in self._exportable_variables():
            pool.addChild(self._leaf_item(var.name))
        self.variable_tree.expandAll()
        self.variable_tree.blockSignals(False)
        self._next_group_id = 1
        self._rebuild_requirement_tree_everything_unassigned()  # old groups no longer apply

    def _variable_groups(self) -> dict[int, tuple[str, list[str]]]:
        """Every custom (non-pool) top-level item in `variable_tree`, as
        {group_id: (name, [variable names])} -- `variable_tree` is the one source of truth for
        which groups exist and what they're called."""
        groups: dict[int, tuple[str, list[str]]] = {}
        for i in range(self.variable_tree.topLevelItemCount()):
            item = self.variable_tree.topLevelItem(i)
            if item.text(0) == _UNASSIGNED_VARIABLES:
                continue
            group_id = item.data(0, _GROUP_ID_ROLE)
            variable_names = [item.child(j).text(0) for j in range(item.childCount())]
            groups[group_id] = (item.text(0), variable_names)
        return groups

    def _rebuild_requirement_tree_everything_unassigned(self) -> None:
        """Rebuilds `requirement_tree` from scratch: "Unassigned Requirements" plus one empty
        group per `variable_tree` group (same group_id, so a later rename still finds it), with
        every leaf requirement starting in the unassigned pool. Called whenever the leaf
        requirement set changes, and whenever `variable_tree`'s own groups are rebuilt from
        scratch (a new variable set invalidates any prior requirement sort too)."""
        leaves = self._leaf_requirements()
        self.requirement_tree.blockSignals(True)
        self.requirement_tree.clear()
        pool = self._header_item(_UNASSIGNED_REQUIREMENTS, editable=False)
        self.requirement_tree.addTopLevelItem(pool)
        for group_id, (name, _variables) in self._variable_groups().items():
            self.requirement_tree.addTopLevelItem(self._header_item(name, editable=False, group_id=group_id))
        for req in leaves:
            pool.addChild(self._leaf_item(req.reqid))
        self.requirement_tree.expandAll()
        self.requirement_tree.blockSignals(False)
        self._requirement_tree_built_for_reqids = frozenset(r.reqid for r in leaves)
        self._refresh_export_group_selector()

    def _requirement_group_item(self, group_id: int) -> QTreeWidgetItem | None:
        for i in range(self.requirement_tree.topLevelItemCount()):
            item = self.requirement_tree.topLevelItem(i)
            if item.data(0, _GROUP_ID_ROLE) == group_id:
                return item
        return None

    def _on_auto_sort_clicked(self) -> None:
        leaves = self._leaf_requirements()
        if not leaves:
            QMessageBox.information(self, "Nothing to sort", "Import a FRET file on page 1 first.")
            return
        groups = self._variable_groups()
        if not groups:
            QMessageBox.information(self, "No groups yet", "Create at least one group above and drag variables into it first.")
            return

        # Keyed by group_id (stringified), not display name -- two groups could share a name
        # after a rename, and auto_sort_requirements only needs a unique label per bucket.
        assigned = auto_sort_requirements(
            {str(group_id): variables for group_id, (_name, variables) in groups.items()}, leaves,
        )

        self.requirement_tree.blockSignals(True)
        self.requirement_tree.clear()
        pool = self._header_item(_UNASSIGNED_REQUIREMENTS, editable=False)
        self.requirement_tree.addTopLevelItem(pool)
        assigned_reqids: set[str] = set()
        for group_id, (name, _variables) in groups.items():
            group_item = self._header_item(name, editable=False, group_id=group_id)
            self.requirement_tree.addTopLevelItem(group_item)
            for reqid in assigned.get(str(group_id), []):
                group_item.addChild(self._leaf_item(reqid))
                assigned_reqids.add(reqid)
        for req in leaves:
            if req.reqid not in assigned_reqids:
                pool.addChild(self._leaf_item(req.reqid))
        self.requirement_tree.expandAll()
        self.requirement_tree.blockSignals(False)
        self._requirement_tree_built_for_reqids = frozenset(r.reqid for r in leaves)
        self._refresh_export_group_selector()

    def _on_add_group_clicked(self) -> None:
        existing_group_count = len(self._variable_groups())
        name, ok = QInputDialog.getText(
            self, "Add group", "Group name:", text=f"Group {existing_group_count + 1}",
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if any(existing_name == name for existing_name, _variables in self._variable_groups().values()):
            QMessageBox.information(self, "Name already used", f'A group named "{name}" already exists -- pick a different name.')
            return
        group_id = self._next_group_id
        self._next_group_id += 1
        self.variable_tree.addTopLevelItem(self._header_item(name, editable=True, group_id=group_id))
        self.requirement_tree.addTopLevelItem(self._header_item(name, editable=False, group_id=group_id))
        self._refresh_export_group_selector()

    def _on_remove_group_clicked(self) -> None:
        item = self.variable_tree.currentItem()
        if item is None or item.parent() is not None:
            QMessageBox.information(self, "No group selected", "Select a group (not a variable) to remove.")
            return
        if item.text(0) == _UNASSIGNED_VARIABLES:
            QMessageBox.information(
                self, "Can't remove this", f'"{_UNASSIGNED_VARIABLES}" is a holding pen, not a deployable group.',
            )
            return

        group_id = item.data(0, _GROUP_ID_ROLE)
        unassigned_variables = self.variable_tree.topLevelItem(0)
        for child in item.takeChildren():
            unassigned_variables.addChild(child)
        self.variable_tree.takeTopLevelItem(self.variable_tree.indexOfTopLevelItem(item))

        requirement_group_item = self._requirement_group_item(group_id)
        if requirement_group_item is not None:
            unassigned_requirements = self.requirement_tree.topLevelItem(0)
            for child in requirement_group_item.takeChildren():
                unassigned_requirements.addChild(child)
            self.requirement_tree.takeTopLevelItem(self.requirement_tree.indexOfTopLevelItem(requirement_group_item))

        self._refresh_export_group_selector()

    def _on_variable_group_renamed(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.parent() is not None:  # only top-level (group) renames matter here
            return
        group_id = item.data(0, _GROUP_ID_ROLE)
        if group_id is None:  # "Unassigned Variables" itself isn't editable, but be defensive
            return
        requirement_group_item = self._requirement_group_item(group_id)
        if requirement_group_item is not None:
            requirement_group_item.setText(0, item.text(0))
        self._refresh_export_group_selector()

    def _refresh_export_group_selector(self) -> None:
        current_name = self.export_group_combo.currentText()
        names = [name for _group_id, (name, _variables) in self._variable_groups().items()]

        self.export_group_combo.blockSignals(True)
        self.export_group_combo.clear()
        self.export_group_combo.addItems(names)
        if current_name in names:
            self.export_group_combo.setCurrentText(current_name)
        self.export_group_combo.blockSignals(False)

    def _group_member_reqids(self, group_name: str) -> list[str]:
        for i in range(self.requirement_tree.topLevelItemCount()):
            item = self.requirement_tree.topLevelItem(i)
            if item.text(0) == group_name:
                return [item.child(j).text(0) for j in range(item.childCount())]
        return []

    def _on_requirement_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Pops up just the variables the clicked requirement references -- a lightweight,
        auto-dismissing tooltip rather than a blocking dialog, so it doesn't get in the way of
        dragging. Ignored for a click on a group header or "Unassigned Requirements" itself
        (only real requirement leaves have a parent)."""
        if item.parent() is None or self.state.fret_import is None:
            return
        req = self.state.fret_import.requirement(item.text(0))
        if req is None:
            return
        text = ", ".join(req.variable_names) if req.variable_names else "(no variables referenced)"
        QToolTip.showText(QCursor.pos(), text, self.requirement_tree)

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
