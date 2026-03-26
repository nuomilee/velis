from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from .config import BOX_MIN_HEIGHT, BOX_MIN_WIDTH, DEFAULT_BOX_HEIGHT, DEFAULT_BOX_WIDTH, GRID_SIZE
from .utils import open_path


class DesktopBox(QFrame):
    refresh_requested = Signal()

    def __init__(self, category: str, directory: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.category = category
        self.directory = directory
        self._drag_offset = QPoint()
        self.setObjectName("desktopBox")
        self.setWindowFlags(Qt.SubWindow)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(BOX_MIN_WIDTH, BOX_MIN_HEIGHT)
        self.resize(DEFAULT_BOX_WIDTH, DEFAULT_BOX_HEIGHT)
        self._build_ui()
        self.reload_files()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel(f"{self.category}盒子")
        self.title_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #333;")
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)

        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self._open_item)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self.file_list)

        grip_row = QHBoxLayout()
        grip_row.addStretch()
        grip = QSizeGrip(self)
        grip_row.addWidget(grip)
        layout.addLayout(grip_row)

        self.setStyleSheet(
            """
            QFrame#desktopBox {
                background: rgba(230, 230, 230, 180);
                border: 1px solid rgba(180, 180, 180, 180);
                border-radius: 18px;
            }
            QListWidget {
                background: rgba(255,255,255,120);
                border: none;
                border-radius: 12px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 6px;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background: rgba(120,120,120,60);
                color: #222;
            }
            """
        )

    def reload_files(self) -> None:
        self.file_list.clear()
        if not self.directory.exists():
            return
        for file_path in sorted(self.directory.iterdir(), key=lambda p: p.name.lower()):
            if file_path.is_file():
                item = QListWidgetItem(file_path.name)
                item.setData(Qt.UserRole, str(file_path))
                self.file_list.addItem(item)

    def _open_item(self, item: QListWidgetItem) -> None:
        file_path = Path(item.data(Qt.UserRole))
        if file_path.exists():
            open_path(file_path)

    def _show_menu(self, pos) -> None:
        menu = QMenu(self)
        open_dir_action = QAction("打开分类目录", self)
        refresh_action = QAction("刷新", self)
        open_dir_action.triggered.connect(lambda: open_path(self.directory))
        refresh_action.triggered.connect(self.reload_files)
        menu.addAction(open_dir_action)
        menu.addAction(refresh_action)
        menu.exec(self.file_list.mapToGlobal(pos))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            new_pos = self.mapToParent(event.pos() - self._drag_offset)
            self.move(self._snap_point(new_pos))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.move(self._snap_point(self.pos()))
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        snapped = self._snap_rect(self.geometry())
        if snapped.size() != self.geometry().size():
            self.setGeometry(snapped)
        super().resizeEvent(event)

    def _snap_point(self, point: QPoint) -> QPoint:
        x = max(0, round(point.x() / GRID_SIZE) * GRID_SIZE)
        y = max(0, round(point.y() / GRID_SIZE) * GRID_SIZE)
        return QPoint(x, y)

    def _snap_rect(self, rect: QRect) -> QRect:
        width = max(BOX_MIN_WIDTH, round(rect.width() / GRID_SIZE) * GRID_SIZE)
        height = max(BOX_MIN_HEIGHT, round(rect.height() / GRID_SIZE) * GRID_SIZE)
        return QRect(self._snap_point(rect.topLeft()), rect.size().expandedTo(rect.size())) if False else QRect(rect.x(), rect.y(), width, height)
