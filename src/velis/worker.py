from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from .ai_classifier import AISettings
from .config import DESKTOP_PATH, ORGANIZE_ROOT
from .organizer import DesktopOrganizer


@dataclass
class OrganizeProgress:
    kind: str
    message: str


class OrganizerWorker(QObject):
    progress = Signal(str)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, settings: AISettings):
        super().__init__()
        self.settings = settings

    @Slot()
    def run(self) -> None:
        try:
            organizer = DesktopOrganizer(DESKTOP_PATH, ORGANIZE_ROOT, self.settings)
            self.progress.emit("开始整理桌面...")
            records = organizer.organize()
            self.finished.emit(records)
        except Exception as exc:
            self.failed.emit(str(exc))
