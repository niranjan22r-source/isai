"""ISAI — a lightweight, Linux-native music player.

Entry point: creates the application, applies the saved theme, and opens the
main window.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from core.resources import resource_path
from core.theme_manager import ThemeManager
from ui.main_window import (
    APP_NAME,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MINIMUM_WINDOW_HEIGHT,
    MINIMUM_WINDOW_WIDTH,
    WINDOW_TITLE,
    MainWindow,
)

__all__ = [
    "APP_NAME",
    "DEFAULT_WINDOW_HEIGHT",
    "DEFAULT_WINDOW_WIDTH",
    "MINIMUM_WINDOW_HEIGHT",
    "MINIMUM_WINDOW_WIDTH",
    "MainWindow",
    "WINDOW_TITLE",
    "create_application",
    "main",
]


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create or return the single QApplication instance."""
    existing = QApplication.instance()
    if existing is not None:
        return existing

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    # Prefer a clean geometric/humanist sans when available. QSS owns the
    # type scale; this only sets the family baseline.
    families = set(QFontDatabase.families())
    for family in (
        "IBM Plex Sans",
        "Source Sans 3",
        "Source Sans Pro",
        "Inter",
        "Cantarell",
        "Noto Sans",
        "Ubuntu",
        "DejaVu Sans",
    ):
        if family in families:
            app.setFont(QFont(family, 10))
            break
    icon_path = resource_path("assets", "icons", "hicolor", "256x256", "apps", "isai.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    return app


def main() -> int:
    app = create_application()
    theme_manager = ThemeManager()
    window = MainWindow(theme_manager)

    screen = app.primaryScreen()
    if screen is not None:
        frame = window.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        window.move(frame.topLeft())

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
