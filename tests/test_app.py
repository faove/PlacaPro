import pytest

from app import create_main_window
from utils.constants import APP_NAME


@pytest.mark.ui
def test_main_window_opens(qtbot):
    window = create_main_window()
    qtbot.addWidget(window)
    window.show()
    assert window.isVisible()
    assert window.windowTitle() == APP_NAME
