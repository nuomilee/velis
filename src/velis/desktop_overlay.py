from __future__ import annotations

import ctypes
import os
from pathlib import Path

from PySide6.QtCore import QFileInfo, QPoint, QRect, QSize, Qt, Signal, QPropertyAnimation, QEvent
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRegion, QCursor, QImage
from PySide6.QtWidgets import QAbstractItemView, QFileIconProvider, QListView, QListWidget, QListWidgetItem, QMenu, QVBoxLayout, QWidget

from .config import BOX_MIN_HEIGHT, BOX_MIN_WIDTH, DEFAULT_BOX_HEIGHT, DEFAULT_BOX_WIDTH, GRID_SIZE
from .utils import extract_audio_cover_icon, open_path, show_system_context_menu

SCREEN_MARGIN = 10
RESIZE_MARGIN = 12
CORNER_MARGIN = 36


class DesktopOverlayBox(QWidget):
    released = Signal(object)
    focused = Signal(object)
    geometry_changed = Signal(object)
    view_style_changed = Signal(object)

    def __init__(self, category: str, directory: Path, opacity_percent: int = 55):
        super().__init__(None)
        self.category = category
        self.directory = directory
        self._drag_offset = QPoint()
        self._dragging = False
        self._resizing = False
        self._pressed_in_resize_zone = False
        self._resize_edges: set[str] = set()
        self._press_geometry = QRect()
        self._press_global_pos = QPoint()
        self._view_style = 'medium'
        self._opacity_percent = opacity_percent
        self._base_color = QColor('#B9BEC3')
        self._selection_color = QColor('#5A5F64')
        self._selection_opacity_percent = 49
        self._blur_enabled = False
        self._icon_provider = QFileIconProvider()
        self._move_anim: QPropertyAnimation | None = None
        self._backdrop_hwnd = None
        self.setWindowTitle(f'{self.category}盒子')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(BOX_MIN_WIDTH, BOX_MIN_HEIGHT)
        self.resize(DEFAULT_BOX_WIDTH, DEFAULT_BOX_HEIGHT)
        self._build_ui()
        self.reload_files()
        self.apply_view_style('medium')
        self.set_opacity_percent(opacity_percent)
        self._apply_round_mask()
        self._apply_blur_effect()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)

        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(self._open_item)
        self.file_list.itemPressed.connect(lambda *_: self.focused.emit(self))
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_file_or_box_menu)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_box_menu)
        self.file_list.setResizeMode(QListWidget.Adjust)
        self.file_list.setMovement(QListWidget.Static)
        self.file_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.file_list.setFrameShape(QListView.NoFrame)
        self._refresh_list_styles()
        layout.addWidget(self.file_list)

        self.file_list.viewport().setMouseTracking(True)
        self.file_list.viewport().installEventFilter(self)
        self.file_list.installEventFilter(self)
        self.setMouseTracking(True)

    def _refresh_list_styles(self) -> None:
        r, g, b, _ = self._selection_color.getRgb()
        text_r, text_g, text_b = self._preferred_text_rgb()
        selected_text_r, selected_text_g, selected_text_b = self._preferred_text_rgb(self._selection_color)
        selection_alpha = max(0, min(255, round(255 * (self._selection_opacity_percent / 100.0))))
        self.file_list.setStyleSheet(
            f"""
            QListWidget {{
                background: transparent;
                border: none;
                padding: 0px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 6px;
                border-radius: 8px;
                color: rgb({text_r}, {text_g}, {text_b});
                background: transparent;
            }}
            QListWidget::item:selected {{
                background: rgba({r}, {g}, {b}, {selection_alpha});
                color: rgb({selected_text_r}, {selected_text_g}, {selected_text_b});
            }}
            QScrollBar:vertical, QScrollBar:horizontal {{
                width: 0px;
                height: 0px;
                background: transparent;
            }}
            """
        )

    def clear_selection(self) -> None:
        self.file_list.clearSelection()
        self.file_list.setCurrentItem(None)
        self.file_list.viewport().update()

    def set_opacity_percent(self, opacity_percent: int) -> None:
        self._opacity_percent = max(0, min(opacity_percent, 100))
        self._refresh_list_styles()
        self._apply_blur_effect()
        self.update()
        self.file_list.viewport().update()

    def set_background_color(self, color_hex: str) -> None:
        color = QColor(color_hex)
        if color.isValid():
            self._base_color = color
            self._refresh_list_styles()
            self._apply_blur_effect()
            self.update()

    def set_selection_color(self, color_hex: str) -> None:
        color = QColor(color_hex)
        if color.isValid():
            self._selection_color = color
            self._refresh_list_styles()

    def set_selection_opacity_percent(self, opacity_percent: int) -> None:
        self._selection_opacity_percent = max(0, min(opacity_percent, 100))
        self._refresh_list_styles()

    def set_blur_enabled(self, enabled: bool) -> None:
        self._blur_enabled = enabled
        self._apply_blur_effect()
        self.update()

    def animate_to(self, point: QPoint) -> None:
        target = self._clamp_to_screen(point)
        self._move_anim = QPropertyAnimation(self, b'pos', self)
        self._move_anim.setDuration(220)
        self._move_anim.setStartValue(self.pos())
        self._move_anim.setEndValue(target)
        self._move_anim.finished.connect(lambda: self.geometry_changed.emit(self))
        self._move_anim.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)
        alpha = int(255 * (self._opacity_percent / 100.0))
        bg = QColor(self._base_color)
        bg.setAlpha(alpha)
        if self._blur_enabled:
            bg.setAlpha(max(0, min(alpha // 8, 10)))
        border = QColor(self._base_color.darker(142))
        border.setAlpha(138)
        painter.setBrush(bg)
        pen = QPen(border)
        pen.setWidthF(0.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRoundedRect(rect.adjusted(0.25, 0.25, -0.25, -0.25), 18, 18)
        super().paintEvent(event)

    def reload_files(self) -> None:
        self.file_list.clear()
        if not self.directory.exists():
            return
        for file_path in sorted(self.directory.iterdir(), key=lambda p: p.name.lower()):
            if file_path.is_file():
                item = QListWidgetItem(file_path.name)
                item.setData(Qt.UserRole, str(file_path))
                item.setIcon(self._file_icon(file_path))
                item.setForeground(QColor(10, 14, 18))
                self.file_list.addItem(item)

    def _file_icon(self, file_path: Path) -> QIcon:
        cover_icon = extract_audio_cover_icon(file_path)
        if cover_icon is not None and not cover_icon.isNull():
            return cover_icon
        shell_icon = self._windows_shell_icon(file_path)
        if shell_icon is not None and not shell_icon.isNull():
            return shell_icon
        fallback = self._icon_provider.icon(QFileInfo(str(file_path)))
        if not fallback.isNull():
            return fallback
        return self._icon_provider.icon(QFileIconProvider.File)

    def _windows_shell_icon(self, file_path: Path) -> QIcon | None:
        try:
            import ctypes.wintypes as wintypes

            SHGFI_ICON = 0x000000100
            SHGFI_SMALLICON = 0x000000001
            SHGFI_USEFILEATTRIBUTES = 0x000000010
            FILE_ATTRIBUTE_NORMAL = 0x00000080

            class SHFILEINFO(ctypes.Structure):
                _fields_ = [
                    ('hIcon', wintypes.HANDLE),
                    ('iIcon', ctypes.c_int),
                    ('dwAttributes', ctypes.c_uint32),
                    ('szDisplayName', ctypes.c_wchar * 260),
                    ('szTypeName', ctypes.c_wchar * 80),
                ]

            shfileinfo = SHFILEINFO()
            flags = SHGFI_ICON | SHGFI_USEFILEATTRIBUTES | SHGFI_SMALLICON
            res = ctypes.windll.shell32.SHGetFileInfoW(
                str(file_path),
                FILE_ATTRIBUTE_NORMAL,
                ctypes.byref(shfileinfo),
                ctypes.sizeof(shfileinfo),
                flags,
            )
            if not res or not shfileinfo.hIcon:
                return None

            pixmap = QPixmap.fromImage(QPixmap.fromWinHICON(int(shfileinfo.hIcon)).toImage())
            ctypes.windll.user32.DestroyIcon(shfileinfo.hIcon)
            if pixmap.isNull():
                return None
            return QIcon(pixmap)
        except Exception:
            return None

    def apply_view_style(self, style_name: str) -> None:
        self._view_style = style_name
        if style_name == 'tile':
            self.file_list.setViewMode(QListWidget.ListMode)
            self.file_list.setFlow(QListWidget.TopToBottom)
            self.file_list.setWrapping(False)
            self.file_list.setIconSize(QSize(18, 18))
            self.file_list.setGridSize(QSize(max(0, self.width() - 24), 30))
            self.file_list.setWordWrap(False)
            self.file_list.setSpacing(0)
            self.file_list.setContentsMargins(0, 0, 0, 0)
        elif style_name == 'small':
            self.file_list.setViewMode(QListWidget.IconMode)
            self.file_list.setFlow(QListWidget.LeftToRight)
            self.file_list.setWrapping(True)
            self.file_list.setIconSize(QSize(18, 18))
            self.file_list.setGridSize(QSize(88, 52))
            self.file_list.setWordWrap(True)
            self.file_list.setSpacing(4)
        elif style_name == 'large':
            self.file_list.setViewMode(QListWidget.IconMode)
            self.file_list.setFlow(QListWidget.LeftToRight)
            self.file_list.setWrapping(True)
            self.file_list.setIconSize(QSize(48, 48))
            self.file_list.setGridSize(QSize(132, 96))
            self.file_list.setWordWrap(True)
            self.file_list.setSpacing(10)
        else:
            self.file_list.setViewMode(QListWidget.IconMode)
            self.file_list.setFlow(QListWidget.LeftToRight)
            self.file_list.setWrapping(True)
            self.file_list.setIconSize(QSize(30, 30))
            self.file_list.setGridSize(QSize(108, 70))
            self.file_list.setWordWrap(True)
            self.file_list.setSpacing(7)

        self.file_list.setTextElideMode(Qt.ElideRight)
        self.file_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.file_list.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.file_list.doItemsLayout()
        self.updateGeometry()
        self.view_style_changed.emit(self)

    def place_at(self, x: int, y: int) -> None:
        self.move(self._snap_point(QPoint(x, y)))

    def geometry_snapshot(self) -> tuple[int, int, int, int]:
        return self.x(), self.y(), self.width(), self.height()

    def _open_item(self, item: QListWidgetItem) -> None:
        file_path = Path(item.data(Qt.UserRole))
        if file_path.exists():
            open_path(file_path)

    def _build_box_menu(self) -> QMenu:
        menu = QMenu(self)
        open_dir_action = QAction('打开分类目录', self)
        refresh_action = QAction('刷新', self)
        show_hidden_action = QAction('显示隐藏盒子', self)

        view_menu = menu.addMenu('展示样式')
        tile_action = QAction('平铺', self)
        small_action = QAction('小图标', self)
        medium_action = QAction('中图标', self)
        large_action = QAction('大图标', self)

        tile_action.triggered.connect(lambda: self.apply_view_style('tile'))
        small_action.triggered.connect(lambda: self.apply_view_style('small'))
        medium_action.triggered.connect(lambda: self.apply_view_style('medium'))
        large_action.triggered.connect(lambda: self.apply_view_style('large'))

        view_menu.addAction(tile_action)
        view_menu.addAction(small_action)
        view_menu.addAction(medium_action)
        view_menu.addAction(large_action)

        close_action = QAction('隐藏盒子', self)
        open_dir_action.triggered.connect(lambda: open_path(self.directory))
        refresh_action.triggered.connect(self.reload_files)
        show_hidden_action.triggered.connect(lambda: self.geometry_changed.emit(('show_all_hidden', self)))
        close_action.triggered.connect(lambda: (self.hide(), self.geometry_changed.emit(self)))

        menu.addAction(open_dir_action)
        menu.addAction(refresh_action)
        menu.addAction(show_hidden_action)
        menu.addSeparator()
        menu.addAction(close_action)
        return menu

    def _show_file_or_box_menu(self, pos) -> None:
        item = self.file_list.itemAt(pos)
        global_pos = self.file_list.mapToGlobal(pos)
        if item is not None:
            file_path = Path(item.data(Qt.UserRole))
            if file_path.exists():
                show_system_context_menu(file_path, global_pos)
            return
        if not bool(QGuiApplication.keyboardModifiers() & Qt.AltModifier):
            return
        menu = self._build_box_menu()
        menu.exec(global_pos)

    def _show_box_menu(self, pos) -> None:
        if not bool(QGuiApplication.keyboardModifiers() & Qt.AltModifier):
            return
        menu = self._build_box_menu()
        menu.exec(self.mapToGlobal(pos))

    def _begin_pointer_action(self, local_pos: QPoint, global_pos: QPoint, modifiers, button) -> bool:
        if button != Qt.LeftButton:
            return False
        self.focused.emit(self)
        self._press_geometry = self.geometry()
        self._press_global_pos = QPoint(global_pos)
        self._resize_edges = self._hit_test_edges(local_pos)
        self._pressed_in_resize_zone = bool(self._resize_edges)
        self._dragging = False
        self._resizing = False

        alt_pressed = bool(modifiers & Qt.AltModifier)
        if alt_pressed and self._pressed_in_resize_zone:
            self._resizing = True
            return True
        if alt_pressed:
            self._dragging = True
            self._drag_offset = QPoint(global_pos) - self.frameGeometry().topLeft()
            return True
        return False

    def _handle_pointer_move(self, local_pos: QPoint, global_pos: QPoint, buttons) -> bool:
        if self._resizing and (buttons & Qt.LeftButton):
            self._perform_resize(QPoint(global_pos))
            return True
        if self._dragging and (buttons & Qt.LeftButton):
            self.move(self._snap_point(QPoint(global_pos) - self._drag_offset))
            return True
        self._update_cursor(local_pos)
        return False

    def _finish_pointer_action(self) -> None:
        if self._dragging:
            self.move(self._snap_point(self.pos()))
        if self._resizing:
            self.setGeometry(self._snap_rect(self.geometry()))
        self._dragging = False
        self._resizing = False
        self._resize_edges = set()
        self._pressed_in_resize_zone = False
        self.unsetCursor()
        self.geometry_changed.emit(self)
        self.released.emit(self)

    def mousePressEvent(self, event):
        if self._begin_pointer_action(event.pos(), event.globalPosition().toPoint(), event.modifiers(), event.button()):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._handle_pointer_move(event.pos(), event.globalPosition().toPoint(), event.buttons()):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging or self._resizing:
            self._finish_pointer_action()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched, event):
        if watched in (self.file_list, self.file_list.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                if self._begin_pointer_action(event.position().toPoint(), event.globalPosition().toPoint(), event.modifiers(), event.button()):
                    event.accept()
                    return True
            elif event.type() == QEvent.MouseMove:
                if self._handle_pointer_move(event.position().toPoint(), event.globalPosition().toPoint(), event.buttons()):
                    event.accept()
                    return True
            elif event.type() == QEvent.MouseButtonRelease:
                if self._dragging or self._resizing:
                    self._finish_pointer_action()
                    event.accept()
                    return True
        return super().eventFilter(watched, event)

    def focusOutEvent(self, event) -> None:
        self.clear_selection()
        super().focusOutEvent(event)

    def resizeEvent(self, event):
        snapped = self._snap_rect(self.geometry())
        if snapped.size() != self.geometry().size() and not self._resizing:
            self.setGeometry(snapped)
        if self._view_style == 'tile':
            self.file_list.setGridSize(QSize(max(0, self.width() - 24), 30))
        self._apply_round_mask()
        if not self._dragging and not self._resizing:
            self.geometry_changed.emit(self)
        super().resizeEvent(event)

    def _hit_test_edges(self, pos: QPoint) -> set[str]:
        x = pos.x()
        y = pos.y()
        width = self.width()
        height = self.height()

        near_left = x <= RESIZE_MARGIN
        near_right = x >= width - RESIZE_MARGIN
        near_top = y <= RESIZE_MARGIN
        near_bottom = y >= height - RESIZE_MARGIN

        in_top_left_corner = x <= CORNER_MARGIN and y <= CORNER_MARGIN
        in_top_right_corner = x >= width - CORNER_MARGIN and y <= CORNER_MARGIN
        in_bottom_left_corner = x <= CORNER_MARGIN and y >= height - CORNER_MARGIN
        in_bottom_right_corner = x >= width - CORNER_MARGIN and y >= height - CORNER_MARGIN

        edges: set[str] = set()
        if near_left:
            edges.add('left')
        if near_right:
            edges.add('right')
        if near_top:
            edges.add('top')
        if near_bottom:
            edges.add('bottom')

        if in_top_left_corner:
            edges.update({'left', 'top'})
        elif in_top_right_corner:
            edges.update({'right', 'top'})
        elif in_bottom_left_corner:
            edges.update({'left', 'bottom'})
        elif in_bottom_right_corner:
            edges.update({'right', 'bottom'})

        return edges

    def _update_cursor(self, pos: QPoint) -> None:
        modifiers = QGuiApplication.keyboardModifiers()
        if not bool(modifiers & Qt.AltModifier):
            self.unsetCursor()
            return
        edges = self._hit_test_edges(pos)
        if edges in ({'left', 'top'}, {'right', 'bottom'}):
            self.setCursor(QCursor(Qt.SizeFDiagCursor))
        elif edges in ({'right', 'top'}, {'left', 'bottom'}):
            self.setCursor(QCursor(Qt.SizeBDiagCursor))
        elif 'left' in edges or 'right' in edges:
            self.setCursor(QCursor(Qt.SizeHorCursor))
        elif 'top' in edges or 'bottom' in edges:
            self.setCursor(QCursor(Qt.SizeVerCursor))
        elif bool(modifiers & Qt.AltModifier):
            self.setCursor(QCursor(Qt.SizeAllCursor))
        else:
            self.unsetCursor()

    def _perform_resize(self, global_pos: QPoint) -> None:
        delta = global_pos - self._press_global_pos
        rect = QRect(self._press_geometry)

        if 'left' in self._resize_edges:
            rect.setLeft(rect.left() + delta.x())
        if 'right' in self._resize_edges:
            rect.setRight(rect.right() + delta.x())
        if 'top' in self._resize_edges:
            rect.setTop(rect.top() + delta.y())
        if 'bottom' in self._resize_edges:
            rect.setBottom(rect.bottom() + delta.y())

        if rect.width() < BOX_MIN_WIDTH:
            if 'left' in self._resize_edges:
                rect.setLeft(rect.right() - BOX_MIN_WIDTH)
            else:
                rect.setWidth(BOX_MIN_WIDTH)
        if rect.height() < BOX_MIN_HEIGHT:
            if 'top' in self._resize_edges:
                rect.setTop(rect.bottom() - BOX_MIN_HEIGHT)
            else:
                rect.setHeight(BOX_MIN_HEIGHT)

        self.setGeometry(self._snap_rect(rect))

    def _apply_blur_effect(self) -> None:
        self._apply_round_mask()
        if os.name != 'nt':
            return
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return

            class ACCENTPOLICY(ctypes.Structure):
                _fields_ = [
                    ('AccentState', ctypes.c_int),
                    ('AccentFlags', ctypes.c_int),
                    ('GradientColor', ctypes.c_uint32),
                    ('AnimationId', ctypes.c_int),
                ]

            class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
                _fields_ = [
                    ('Attribute', ctypes.c_int),
                    ('Data', ctypes.c_void_p),
                    ('SizeOfData', ctypes.c_size_t),
                ]

            accent = ACCENTPOLICY()
            if self._blur_enabled:
                base = QColor(self._base_color)
                alpha = max(8, min(int(255 * (self._opacity_percent / 100.0) * 0.7), 120))
                gradient = (alpha << 24) | (base.blue() << 16) | (base.green() << 8) | base.red()
                accent.AccentState = 4
                accent.AccentFlags = 0
                accent.GradientColor = gradient
            else:
                accent.AccentState = 0
                accent.AccentFlags = 0
                accent.GradientColor = 0
            data = WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = 19
            data.Data = ctypes.addressof(accent)
            data.SizeOfData = ctypes.sizeof(accent)
            ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        except Exception:
            pass

    def _preferred_text_rgb(self, bg_color: QColor | None = None) -> tuple[int, int, int]:
        sample = bg_color if bg_color is not None else self._base_color
        effective_alpha = max(0.08, self._opacity_percent / 100.0)
        r = round(sample.red() * effective_alpha + 245 * (1 - effective_alpha))
        g = round(sample.green() * effective_alpha + 245 * (1 - effective_alpha))
        b = round(sample.blue() * effective_alpha + 245 * (1 - effective_alpha))
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return (8, 10, 14) if luminance > 162 else (245, 247, 250)

    def _apply_round_mask(self) -> None:
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 18, 18)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)

    def _screen_bounds(self) -> QRect:
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            return QRect(
                geo.left() + SCREEN_MARGIN,
                geo.top() + SCREEN_MARGIN,
                max(0, geo.width() - SCREEN_MARGIN * 2),
                max(0, geo.height() - SCREEN_MARGIN * 2),
            )
        return QRect(SCREEN_MARGIN, SCREEN_MARGIN, 1600, 900)

    def _clamp_to_screen(self, point: QPoint) -> QPoint:
        geo = self._screen_bounds()
        max_x = geo.right() - self.width()
        max_y = geo.bottom() - self.height()
        x = max(geo.left(), min(point.x(), max_x))
        y = max(geo.top(), min(point.y(), max_y))
        return QPoint(x, y)

    def _snap_point(self, point: QPoint) -> QPoint:
        clamped = self._clamp_to_screen(point)
        x = round(clamped.x() / GRID_SIZE) * GRID_SIZE
        y = round(clamped.y() / GRID_SIZE) * GRID_SIZE
        return self._clamp_to_screen(QPoint(x, y))

    def _snap_rect(self, rect: QRect) -> QRect:
        width = max(BOX_MIN_WIDTH, round(rect.width() / GRID_SIZE) * GRID_SIZE)
        height = max(BOX_MIN_HEIGHT, round(rect.height() / GRID_SIZE) * GRID_SIZE)
        clamped_pos = self._clamp_to_screen(QPoint(rect.x(), rect.y()))
        return QRect(clamped_pos.x(), clamped_pos.y(), width, height)
