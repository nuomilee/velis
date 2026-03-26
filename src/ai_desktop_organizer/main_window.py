from pathlib import Path
import uuid

from PySide6.QtCore import QPoint, QRect, QThread, Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .ai_classifier import AISettings, load_ai_settings, save_ai_settings
from .config import AI_SETTINGS_PATH, APP_NAME, DESKTOP_PATH, ORGANIZE_ROOT, UI_SETTINGS_PATH
from .desktop_overlay import DesktopOverlayBox
from .organizer import DesktopOrganizer
from .ui_state import BoxState, load_ui_settings, save_ui_settings
from .worker import OrganizerWorker


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.ai_settings = load_ai_settings(AI_SETTINGS_PATH)
        self.ui_settings = load_ui_settings(UI_SETTINGS_PATH)
        self.organizer = DesktopOrganizer(DESKTOP_PATH, ORGANIZE_ROOT, self.ai_settings)
        self.boxes: list[DesktopOverlayBox] = []
        self.box_uid_by_directory: dict[str, str] = {}
        self.organize_thread: QThread | None = None
        self.organize_worker: OrganizerWorker | None = None
        self.box_opacity_percent = self.ui_settings.opacity_percent
        self.box_background_color = self.ui_settings.background_color
        self.selection_color = self.ui_settings.selection_color
        self.selection_opacity_percent = self.ui_settings.selection_opacity_percent
        self.blur_enabled = self.ui_settings.blur_enabled
        self._quitting = False
        self.setWindowTitle(APP_NAME)
        self.resize(self.ui_settings.window_width, self.ui_settings.window_height)
        self.move(self.ui_settings.window_x, self.ui_settings.window_y)
        self._build_ui()
        self._build_tray()
        self.app.focusChanged.connect(lambda *_: self._clear_all_box_selections())
        self._load_settings_to_ui()
        self._apply_window_style()
        self.refresh_boxes()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        hero = QFrame()
        hero.setObjectName('heroCard')
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 16, 18, 16)
        hero_layout.setSpacing(10)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(2)
        title = QLabel('AI桌面整理')
        title.setObjectName('heroTitle')
        subtitle = QLabel('更优雅地整理桌面文件与分类盒子')
        subtitle.setObjectName('heroSubtitle')
        hero_text.addWidget(title)
        hero_text.addWidget(subtitle)
        hero_layout.addLayout(hero_text)
        hero_layout.addStretch()
        self.organize_btn = QPushButton('开始整理')
        self.organize_btn.clicked.connect(self.organize_desktop)
        self.refresh_btn = QPushButton('刷新盒子')
        self.refresh_btn.clicked.connect(self.refresh_boxes)
        self.save_ai_btn = QPushButton('保存配置')
        self.save_ai_btn.clicked.connect(self.save_ai_config)
        hero_layout.addWidget(self.organize_btn)
        hero_layout.addWidget(self.refresh_btn)
        hero_layout.addWidget(self.save_ai_btn)
        root.addWidget(hero)

        content = QHBoxLayout()
        content.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(14)

        ai_group = QGroupBox('AI 设置')
        ai_layout = QFormLayout(ai_group)
        ai_layout.setSpacing(8)
        ai_layout.setHorizontalSpacing(12)
        ai_layout.setVerticalSpacing(8)
        ai_layout.setLabelAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        ai_layout.setFormAlignment(Qt.AlignTop)
        ai_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.ai_enabled = QCheckBox('启用 AI 重命名与分类（失败则跳过重命名）')
        ai_layout.addRow('AI分类', self.ai_enabled)
        self.ai_mode = QComboBox()
        self.ai_mode.addItems(['local', 'online'])
        ai_layout.addRow('分析模式', self.ai_mode)
        self.local_base_url = QLineEdit()
        self.local_model = QLineEdit()
        self.online_base_url = QLineEdit()
        self.online_api_key = QLineEdit()
        self.online_api_key.setEchoMode(QLineEdit.Password)
        self.online_model = QLineEdit()
        self.timeout_seconds = QLineEdit()
        ai_layout.addRow('本地 Base URL', self.local_base_url)
        ai_layout.addRow('本地模型', self.local_model)
        ai_layout.addRow('在线 Base URL', self.online_base_url)
        ai_layout.addRow('在线 API Key', self.online_api_key)
        ai_layout.addRow('在线模型', self.online_model)
        ai_layout.addRow('超时秒数', self.timeout_seconds)
        left_col.addWidget(ai_group)

        box_group = QGroupBox('盒子外观')
        box_layout = QFormLayout(box_group)
        box_layout.setSpacing(8)
        box_layout.setHorizontalSpacing(12)
        box_layout.setVerticalSpacing(8)
        box_layout.setLabelAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        box_layout.setFormAlignment(Qt.AlignTop)
        box_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(self.box_opacity_percent)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_label = QLabel(f'{self.box_opacity_percent}%')
        opacity_row = QHBoxLayout()
        opacity_row.setContentsMargins(0, 0, 0, 0)
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_label)
        opacity_wrap = QWidget()
        opacity_wrap.setLayout(opacity_row)
        box_layout.addRow('背景透明度', opacity_wrap)

        self.color_preview = QLabel('      ')
        self.color_preview.setFixedSize(40, 28)
        self.color_btn = QPushButton('背景色')
        self.color_btn.clicked.connect(self._pick_color)
        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.addWidget(self.color_preview)
        color_row.addWidget(self.color_btn)
        color_row.addStretch()
        color_wrap = QWidget()
        color_wrap.setLayout(color_row)
        box_layout.addRow('盒子背景色', color_wrap)

        self.selection_preview = QLabel('      ')
        self.selection_preview.setFixedSize(40, 28)
        self.selection_btn = QPushButton('选中颜色')
        self.selection_btn.clicked.connect(self._pick_selection_color)
        select_row = QHBoxLayout()
        select_row.setContentsMargins(0, 0, 0, 0)
        select_row.addWidget(self.selection_preview)
        select_row.addWidget(self.selection_btn)
        select_row.addStretch()
        select_wrap = QWidget()
        select_wrap.setLayout(select_row)
        box_layout.addRow('选中项颜色', select_wrap)

        self.selection_opacity_slider = QSlider(Qt.Horizontal)
        self.selection_opacity_slider.setRange(0, 100)
        self.selection_opacity_slider.setValue(self.selection_opacity_percent)
        self.selection_opacity_slider.valueChanged.connect(self._on_selection_opacity_changed)
        self.selection_opacity_label = QLabel(f'{self.selection_opacity_percent}%')
        selection_opacity_row = QHBoxLayout()
        selection_opacity_row.setContentsMargins(0, 0, 0, 0)
        selection_opacity_row.addWidget(self.selection_opacity_slider)
        selection_opacity_row.addWidget(self.selection_opacity_label)
        selection_opacity_wrap = QWidget()
        selection_opacity_wrap.setLayout(selection_opacity_row)
        box_layout.addRow('选中透明度', selection_opacity_wrap)

        self.blur_checkbox = QCheckBox('启用盒子背景高斯模糊')
        self.blur_checkbox.toggled.connect(self._on_blur_toggled)
        box_layout.addRow('背景模糊', self.blur_checkbox)

        left_col.addWidget(box_group)
        left_col.addStretch()

        right_col = QVBoxLayout()
        right_col.setSpacing(14)
        log_group = QGroupBox('运行日志')
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(12, 12, 12, 12)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText('这里会显示整理日志、盒子状态与系统提示...')
        log_layout.addWidget(self.log)
        right_col.addWidget(log_group, 1)

        content.addLayout(left_col, 5)
        content.addLayout(right_col, 4)
        root.addLayout(content, 1)

    def _build_tray(self) -> None:
        icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self._rebuild_tray_menu()
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _rebuild_tray_menu(self) -> None:
        menu = QMenu(self)
        show_boxes_action = QAction('显示盒子', self)
        show_window_action = QAction('显示窗口', self)
        quit_action = QAction('退出', self)
        show_boxes_action.triggered.connect(self._show_all_hidden_boxes)
        show_window_action.triggered.connect(self.showNormal)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(show_boxes_action)
        menu.addAction(show_window_action)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)

    def _apply_window_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f6f8fb; }
            QFrame#heroCard {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #ffffff, stop:1 #f4f7fb);
                border: 1px solid #e7ebf0;
                border-radius: 16px;
            }
            QLabel#heroTitle {
                font-size: 20px;
                font-weight: 700;
                color: #111827;
                background: transparent;
                border: none;
                min-height: 26px;
            }
            QLabel#heroSubtitle {
                font-size: 12px;
                color: #6b7280;
                background: transparent;
                border: none;
                min-height: 20px;
            }
            QGroupBox {
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                margin-top: 10px;
                background: rgba(255,255,255,232);
                font-weight: 600;
                color: #111827;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLabel {
                background: transparent;
                border: none;
                min-height: 28px;
                color: #111827;
            }
            QPushButton {
                min-height: 34px;
                max-height: 34px;
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                padding: 0 14px;
                color: #111827;
            }
            QPushButton:hover { background: #f9fafb; }
            QPushButton:pressed { background: #eef2f7; }
            QLineEdit, QComboBox {
                min-height: 30px;
                max-height: 30px;
                border: 1px solid #d1d5db;
                border-radius: 9px;
                padding: 4px 8px;
                background: white;
                color: #111827;
            }
            QTextEdit {
                border: 1px solid #d1d5db;
                border-radius: 10px;
                padding: 10px;
                background: white;
                color: #111827;
            }
            QSlider {
                min-height: 28px;
                max-height: 28px;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #dbe3ef;
                border-radius: 3px;
                margin: 0 0;
            }
            QSlider::handle:horizontal {
                background: #6b7280;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QTextEdit {
                padding: 10px;
            }
            """
        )

    def _load_settings_to_ui(self) -> None:
        s = self.ai_settings
        self.ai_enabled.setChecked(s.enabled)
        self.ai_mode.setCurrentText(s.mode)
        self.local_base_url.setText(s.local_base_url)
        self.local_model.setText(s.local_model)
        self.online_base_url.setText(s.online_base_url)
        self.online_api_key.setText(s.online_api_key)
        self.online_model.setText(s.online_model)
        self.timeout_seconds.setText(str(s.timeout_seconds))
        self.opacity_slider.setValue(self.box_opacity_percent)
        self.opacity_label.setText(f'{self.box_opacity_percent}%')
        self.color_preview.setStyleSheet(f'background:{self.box_background_color}; border-radius:6px; border:1px solid #cbd5e1;')
        self.selection_preview.setStyleSheet(f'background:{self.selection_color}; border-radius:6px; border:1px solid #cbd5e1;')
        self.selection_opacity_slider.setValue(self.selection_opacity_percent)
        self.selection_opacity_label.setText(f'{self.selection_opacity_percent}%')
        self.blur_checkbox.setChecked(self.blur_enabled)

    def _read_settings_from_ui(self) -> AISettings:
        return AISettings(
            enabled=self.ai_enabled.isChecked(),
            mode=self.ai_mode.currentText(),
            local_base_url=self.local_base_url.text().strip(),
            local_model=self.local_model.text().strip(),
            online_base_url=self.online_base_url.text().strip(),
            online_api_key=self.online_api_key.text().strip(),
            online_model=self.online_model.text().strip(),
            timeout_seconds=int(self.timeout_seconds.text().strip() or '20'),
        )

    def save_ai_config(self) -> None:
        try:
            self.ai_settings = self._read_settings_from_ui()
            save_ai_settings(AI_SETTINGS_PATH, self.ai_settings)
            self._save_ui_state()
            self.organizer = DesktopOrganizer(DESKTOP_PATH, ORGANIZE_ROOT, self.ai_settings)
            self.log.append(f'配置已保存：模式={self.ai_settings.mode}，本地模型={self.ai_settings.local_model}，透明度={self.box_opacity_percent}%')
        except Exception as exc:
            QMessageBox.critical(self, '错误', f'保存配置失败：{exc}')

    def _save_ui_state(self) -> None:
        self.ui_settings.opacity_percent = self.box_opacity_percent
        self.ui_settings.background_color = self.box_background_color
        self.ui_settings.selection_color = self.selection_color
        self.ui_settings.selection_opacity_percent = self.selection_opacity_percent
        self.ui_settings.blur_enabled = self.blur_enabled
        self.ui_settings.window_width = self.width()
        self.ui_settings.window_height = self.height()
        self.ui_settings.window_x = self.x()
        self.ui_settings.window_y = self.y()
        box_states: dict[str, BoxState] = {}
        current_directory_keys: set[str] = set()
        for box in self.boxes:
            directory_key = str(box.directory.resolve())
            current_directory_keys.add(directory_key)
            box_uid = getattr(box, 'box_uid', '') or self.box_uid_by_directory.get(directory_key) or str(uuid.uuid4())
            self.box_uid_by_directory[directory_key] = box_uid
            box.box_uid = box_uid
            box_states[box_uid] = BoxState(
                uid=box_uid,
                x=box.x(),
                y=box.y(),
                width=box.width(),
                height=box.height(),
                view_style=getattr(box, '_view_style', 'medium'),
                category=box.category,
                directory=directory_key,
            )

        stale_keys = [key for key in self.box_uid_by_directory if key not in current_directory_keys]
        for key in stale_keys:
            self.box_uid_by_directory.pop(key, None)

        self.ui_settings.boxes = box_states
        save_ui_settings(UI_SETTINGS_PATH, self.ui_settings)
        self._rebuild_tray_menu()

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.box_background_color), self, '选择盒子背景色')
        if not color.isValid():
            return
        self.box_background_color = color.name().upper()
        self.color_preview.setStyleSheet(f'background:{self.box_background_color}; border-radius:6px; border:1px solid #cbd5e1;')
        for box in self.boxes:
            box.set_background_color(self.box_background_color)
        self._save_ui_state()

    def _pick_selection_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.selection_color), self, '选择选中项颜色')
        if not color.isValid():
            return
        self.selection_color = color.name().upper()
        self.selection_preview.setStyleSheet(f'background:{self.selection_color}; border-radius:6px; border:1px solid #cbd5e1;')
        for box in self.boxes:
            box.set_selection_color(self.selection_color)
        self._save_ui_state()

    def _on_selection_opacity_changed(self, value: int) -> None:
        self.selection_opacity_percent = value
        self.selection_opacity_label.setText(f'{value}%')
        for box in self.boxes:
            box.set_selection_opacity_percent(value)
        self._save_ui_state()

    def _on_blur_toggled(self, checked: bool) -> None:
        self.blur_enabled = checked
        for box in self.boxes:
            box.set_blur_enabled(checked)
        self._save_ui_state()

    def _on_opacity_changed(self, value: int) -> None:
        self.box_opacity_percent = value
        self.opacity_label.setText(f'{value}%')
        for box in self.boxes:
            box.set_opacity_percent(value)
        self._save_ui_state()

    def organize_desktop(self) -> None:
        if self.organize_thread is not None:
            QMessageBox.information(self, '提示', '整理任务正在进行中，请稍等。')
            return

        settings = self._read_settings_from_ui()
        self.organize_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.save_ai_btn.setEnabled(False)
        self.log.append('开始整理任务，处理中...')

        self.organize_thread = QThread(self)
        self.organize_worker = OrganizerWorker(settings)
        self.organize_worker.moveToThread(self.organize_thread)
        self.organize_thread.started.connect(self.organize_worker.run)
        self.organize_worker.progress.connect(self.log.append)
        self.organize_worker.finished.connect(self._on_organize_finished)
        self.organize_worker.failed.connect(self._on_organize_failed)
        self.organize_worker.finished.connect(self.organize_thread.quit)
        self.organize_worker.failed.connect(self.organize_thread.quit)
        self.organize_thread.finished.connect(self._cleanup_worker)
        self.organize_thread.start()

    def _on_organize_finished(self, records: list) -> None:
        self.organizer = DesktopOrganizer(DESKTOP_PATH, ORGANIZE_ROOT, self._read_settings_from_ui())
        if not records:
            self.log.append('桌面上没有可整理的文件。')
            self.refresh_boxes()
            return

        self.log.append('开始整理完成：')
        for record in records:
            status = 'AI/元数据命名' if record.renamed_by_ai else ('AI失败，已跳过重命名' if record.new_name == '(未重命名)' else '规则模式')
            self.log.append(f'- [{record.category}] {record.original_path.name} -> {record.new_name} ({status})')
            if record.resolved_target_path:
                self.log.append(f'    lnk真实目标: {record.resolved_target_path}')
            if record.classification_reason:
                self.log.append(f'    分类依据: {record.classification_reason}')
            if record.ai_summary:
                self.log.append(f'    AI分析: {record.ai_summary}')
        self.log.append('')
        self.refresh_boxes()

    def _on_organize_failed(self, message: str) -> None:
        self.log.append(f'整理失败：{message}')
        QMessageBox.critical(self, '错误', f'整理失败：{message}')

    def _cleanup_worker(self) -> None:
        self.organize_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.save_ai_btn.setEnabled(True)
        if self.organize_worker is not None:
            self.organize_worker.deleteLater()
            self.organize_worker = None
        if self.organize_thread is not None:
            self.organize_thread.deleteLater()
            self.organize_thread = None

    def refresh_boxes(self) -> None:
        previous_boxes = list(self.boxes)
        for box in previous_boxes:
            box.close()
            box.deleteLater()
        self.boxes.clear()

        self.ui_settings = load_ui_settings(UI_SETTINGS_PATH)
        categories = self.organizer.existing_categories()
        if not categories:
            self.log.append('当前没有可显示的桌面盒子分类。')
            return

        existing_state_by_directory = {
            state.directory: state for state in self.ui_settings.boxes.values() if getattr(state, 'directory', '')
        }
        pending_boxes: list[DesktopOverlayBox] = []
        x, y = 24, 80
        for category in categories:
            directory = ORGANIZE_ROOT / category
            directory_key = str(directory.resolve())
            box = DesktopOverlayBox(category, directory, opacity_percent=self.box_opacity_percent)
            box.set_background_color(self.box_background_color)
            box.set_selection_color(self.selection_color)
            box.set_selection_opacity_percent(self.selection_opacity_percent)
            box.set_blur_enabled(self.blur_enabled)
            state = existing_state_by_directory.get(directory_key)
            if state is None:
                state = BoxState(uid=self.box_uid_by_directory.get(directory_key, str(uuid.uuid4())), category=category, directory=directory_key, x=x, y=y)
            box.box_uid = state.uid or self.box_uid_by_directory.get(directory_key) or str(uuid.uuid4())
            self.box_uid_by_directory[directory_key] = box.box_uid
            box.resize(state.width, state.height)
            box.place_at(state.x, state.y)
            box.apply_view_style(state.view_style)
            box.released.connect(self._resolve_overlap_for_box)
            box.geometry_changed.connect(self._handle_box_geometry_event)
            box.view_style_changed.connect(self._save_ui_state)
            box.focused.connect(self._on_box_focused)
            pending_boxes.append(box)
            x += box.width() + 18
            if x > 1200:
                x = 24
                y += box.height() + 18

        self.boxes = pending_boxes
        for box in self.boxes:
            box.show()
        self._rebuild_tray_menu()
        self.log.append(f'已刷新桌面盒子：{len(self.boxes)} 个')
        self._save_ui_state()

    def _show_hidden_box_by_uid(self, box_uid: str) -> None:
        if not box_uid:
            return
        for box in self.boxes:
            if getattr(box, 'box_uid', None) == box_uid:
                box.show()
                box.raise_()
                box.activateWindow()
                break
        self._rebuild_tray_menu()
        self._save_ui_state()

    def _show_all_hidden_boxes(self) -> None:
        for box in self.boxes:
            if not box.isVisible():
                box.show()
                box.raise_()
                box.activateWindow()
        self._rebuild_tray_menu()
        self._save_ui_state()

    def _handle_box_geometry_event(self, payload) -> None:
        if isinstance(payload, tuple) and payload and payload[0] == 'show_all_hidden':
            self._show_all_hidden_boxes()
            return
        self._save_ui_state()

    def _clear_all_box_selections(self) -> None:
        for box in self.boxes:
            box.clear_selection()

    def _on_box_focused(self, active_box: DesktopOverlayBox) -> None:
        for box in self.boxes:
            if box is not active_box:
                box.clear_selection()

    def _find_non_overlapping_grid_position(self, moving_box: DesktopOverlayBox) -> QPoint:
        others = [b for b in self.boxes if b is not moving_box and b.isVisible()]
        padding = 10
        current_rect = moving_box.geometry().adjusted(0, 0, -1, -1)
        if all(not current_rect.intersects(other.geometry().adjusted(0, 0, -1, -1)) for other in others):
            return moving_box.pos()

        screen = moving_box._screen_bounds()
        step = 5
        start_x = moving_box.x()
        start_y = moving_box.y()
        best_point = moving_box.pos()
        best_score: tuple[int, int, int, int] | None = None

        occupied: list[QRect] = [other.geometry().adjusted(-padding, -padding, padding, padding) for other in others]
        max_x = max(screen.left(), screen.right() - moving_box.width())
        max_y = max(screen.top(), screen.bottom() - moving_box.height())

        for y in range(screen.top(), max_y + 1, step):
            for x in range(screen.left(), max_x + 1, step):
                snapped = moving_box._snap_point(QPoint(x, y))
                test_rect = QRect(snapped.x(), snapped.y(), moving_box.width(), moving_box.height())
                if any(test_rect.intersects(rect) for rect in occupied):
                    continue
                dx = snapped.x() - start_x
                dy = snapped.y() - start_y
                right_alignment_penalty = abs((snapped.x() + moving_box.width()) - (start_x + moving_box.width()))
                left_alignment_penalty = abs(snapped.x() - start_x)
                score = (abs(dx) + abs(dy), right_alignment_penalty, left_alignment_penalty, abs(dy), abs(dx))
                if best_score is None or score < best_score:
                    best_score = score
                    best_point = snapped

        return best_point

    def _resolve_overlap_for_box(self, moving_box: DesktopOverlayBox) -> None:
        if not moving_box.isVisible():
            self._save_ui_state()
            return
        target = self._find_non_overlapping_grid_position(moving_box)
        if target != moving_box.pos():
            moving_box.animate_to(target)
        self._save_ui_state()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._quitting = True
        self._save_ui_state()
        self.tray.hide()
        self.close()
        self.app.quit()

    def mousePressEvent(self, event) -> None:
        self._clear_all_box_selections()
        super().mousePressEvent(event)

    def closeEvent(self, event) -> None:
        if self._quitting:
            self._save_ui_state()
            super().closeEvent(event)
            return
        self._save_ui_state()
        self.hide()
        self.tray.showMessage('AI桌面整理', '已最小化到托盘，可从托盘恢复。', QSystemTrayIcon.Information, 2000)
        event.ignore()
