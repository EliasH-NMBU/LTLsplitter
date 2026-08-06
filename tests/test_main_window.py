from PySide6.QtCore import Qt

from ltlsplitter.gui.main_window import PAGE_CLASSES, MainWindow


def test_main_window_has_one_page_per_pipeline_stage(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.stack.count() == len(PAGE_CLASSES) == 6


def test_navigation_enables_and_disables_buttons(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert not window.back_button.isEnabled()
    assert window.next_button.isEnabled()

    qtbot.mouseClick(window.next_button, Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 1
    assert window.back_button.isEnabled()

    for _ in range(len(PAGE_CLASSES) - 1):
        window.go_next()
    assert not window.next_button.isEnabled()
