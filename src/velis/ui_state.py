from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BoxState:
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    x: int = 24
    y: int = 80
    width: int = 280
    height: int = 260
    view_style: str = 'medium'
    category: str = ''
    directory: str = ''


@dataclass
class UISettings:
    opacity_percent: int = 55
    background_color: str = '#B9BEC3'
    selection_color: str = '#5A5F64'
    selection_opacity_percent: int = 49
    blur_enabled: bool = False
    window_width: int = 760
    window_height: int = 640
    window_x: int = 120
    window_y: int = 120
    boxes: dict[str, BoxState] = field(default_factory=dict)


def ui_settings_to_dict(settings: UISettings) -> dict[str, Any]:
    data = asdict(settings)
    data['boxes'] = {k: asdict(v) for k, v in settings.boxes.items()}
    return data


def ui_settings_from_dict(data: dict[str, Any] | None) -> UISettings:
    data = data or {}
    raw_boxes = data.get('boxes', {}) or {}
    boxes: dict[str, BoxState] = {}
    if isinstance(raw_boxes, dict):
        for key, value in raw_boxes.items():
            if isinstance(value, dict):
                boxes[key] = BoxState(
                    uid=str(value.get('uid', key) or key),
                    x=int(value.get('x', 24)),
                    y=int(value.get('y', 80)),
                    width=int(value.get('width', 280)),
                    height=int(value.get('height', 260)),
                    view_style=str(value.get('view_style', 'medium') or 'medium'),
                    category=str(value.get('category', '') or ''),
                    directory=str(value.get('directory', '') or ''),
                )
    return UISettings(
        opacity_percent=int(data.get('opacity_percent', 55) or 55),
        background_color=str(data.get('background_color', '#B9BEC3') or '#B9BEC3'),
        selection_color=str(data.get('selection_color', '#5A5F64') or '#5A5F64'),
        selection_opacity_percent=int(data.get('selection_opacity_percent', 49) or 49),
        blur_enabled=bool(data.get('blur_enabled', False)),
        window_width=int(data.get('window_width', 760) or 760),
        window_height=int(data.get('window_height', 640) or 640),
        window_x=int(data.get('window_x', 120) or 120),
        window_y=int(data.get('window_y', 120) or 120),
        boxes=boxes,
    )


def load_ui_settings(path: Path) -> UISettings:
    if not path.exists():
        settings = UISettings()
        save_ui_settings(path, settings)
        return settings
    try:
        return ui_settings_from_dict(json.loads(path.read_text(encoding='utf-8')))
    except Exception:
        settings = UISettings()
        save_ui_settings(path, settings)
        return settings


def save_ui_settings(path: Path, settings: UISettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ui_settings_to_dict(settings), ensure_ascii=False, indent=2), encoding='utf-8')
