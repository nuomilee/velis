import sys

from PySide6.QtWidgets import QApplication, QStyle

from .main_window import MainWindow


def run() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName('AI Desktop Organizer')
    app.setStyle('Fusion')
    window = MainWindow(app)
    window.show()
    sys.exit(app.exec())
