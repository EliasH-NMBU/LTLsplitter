from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.deployment import DeploymentPage


def test_on_show_without_monitor_prompts_to_go_back(qtbot):
    state = ProjectState()
    page = DeploymentPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert "stage 5" in page.package_label.text()


def test_on_show_with_monitor_shows_path(qtbot):
    state = ProjectState(generated_monitor_path="/tmp/pkg")
    page = DeploymentPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert "/tmp/pkg" in page.package_label.text()


def test_start_without_monitor_shows_message(qtbot, monkeypatch):
    shown = {}
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.deployment.QMessageBox.information",
        lambda *a, **kw: shown.setdefault("called", True),
    )
    state = ProjectState()
    page = DeploymentPage(state)
    qtbot.addWidget(page)

    page._on_start_clicked()

    assert shown.get("called")


def test_start_reports_not_implemented_and_leaves_buttons_unchanged(qtbot):
    state = ProjectState(generated_monitor_path="/tmp/pkg")
    page = DeploymentPage(state)
    qtbot.addWidget(page)

    page._on_start_clicked()

    assert "not implemented" in page.log.toPlainText().lower()
    assert page.start_button.isEnabled()
    assert not page.stop_button.isEnabled()
    assert page._deployment is None
