import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
import ctypes

import base64

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None


INVALID_FILENAME_CHARS = r'[\\/:*?"<>|]'
AUDIO_EXTENSIONS = {'.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg'}


def clean_filename(name: str) -> str:
    stem = re.sub(INVALID_FILENAME_CHARS, '_', name)
    stem = stem.replace('_-_', ' - ')
    stem = re.sub(r'\s*-\s*', ' - ', stem)
    stem = re.sub(r'[ \t]+', ' ', stem.strip())
    stem = re.sub(r'_{2,}', '_', stem)
    return stem.strip(' ._') or 'untitled'


def now_timestamp() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def open_path(path: Path) -> None:
    if os.name == 'nt':
        os.startfile(str(path))
    else:
        subprocess.Popen(['xdg-open', str(path)])


def show_system_context_menu(path: Path, global_pos) -> None:
    if os.name != 'nt' or not path.exists():
        return
    try:
        subprocess.Popen(['explorer.exe', f'/select,{str(path)}'])
    except Exception:
        return


def resolve_windows_shortcut(path: Path) -> Optional[Path]:
    if os.name != 'nt' or path.suffix.lower() != '.lnk':
        return None

    escaped_path = str(path).replace("'", "''")
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $shell.CreateShortcut('{escaped_path}'); "
        "if ($shortcut.TargetPath) { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Write-Output $shortcut.TargetPath }"
    )
    try:
        completed = subprocess.run(
            ['powershell.exe', '-NoProfile', '-Command', script],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=10,
            check=False,
        )
        target = (completed.stdout or '').strip()
        return Path(target) if target else None
    except Exception:
        return None


def read_audio_metadata(path: Path) -> dict[str, str]:
    if MutagenFile is None or path.suffix.lower() not in AUDIO_EXTENSIONS:
        return {}

    try:
        audio = MutagenFile(str(path), easy=True)
        if not audio:
            return {}
        title = _pick_first(audio.get('title'))
        artist = _pick_first(audio.get('artist')) or _pick_first(audio.get('albumartist'))
        album = _pick_first(audio.get('album'))
        return {k: v for k, v in {
            'title': title,
            'artist': artist,
            'album': album,
        }.items() if v}
    except Exception:
        return {}


def extract_audio_cover_icon(path: Path) -> QIcon | None:
    if MutagenFile is None or path.suffix.lower() not in AUDIO_EXTENSIONS:
        return None

    try:
        audio = MutagenFile(str(path))
        if not audio:
            return None

        artwork_candidates: list[bytes] = []
        tags = getattr(audio, 'tags', None)
        if tags:
            if hasattr(tags, 'getall'):
                for key in ('APIC', 'covr', 'METADATA_BLOCK_PICTURE'):
                    for value in tags.getall(key):
                        if hasattr(value, 'data'):
                            artwork_candidates.append(value.data)
                        elif isinstance(value, (bytes, bytearray)):
                            artwork_candidates.append(bytes(value))
                        elif isinstance(value, list):
                            for item in value:
                                if hasattr(item, 'data'):
                                    artwork_candidates.append(item.data)
                                elif isinstance(item, (bytes, bytearray)):
                                    artwork_candidates.append(bytes(item))
            for key, value in getattr(tags, 'items', lambda: [])():
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if hasattr(item, 'data'):
                        artwork_candidates.append(item.data)
                    elif isinstance(item, (bytes, bytearray)):
                        artwork_candidates.append(bytes(item))
                    elif isinstance(item, str) and item.strip().startswith('data:image'):
                        try:
                            payload = item.split(',', 1)[1]
                            artwork_candidates.append(base64.b64decode(payload))
                        except Exception:
                            pass

        for artwork_data in artwork_candidates:
            pixmap = QPixmap()
            if pixmap.loadFromData(artwork_data):
                if pixmap.width() > 0 and pixmap.height() > 0:
                    icon_pixmap = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    return QIcon(icon_pixmap)
                return QIcon(pixmap)
        return None
    except Exception:
        return None


def _pick_first(value) -> str:
    if isinstance(value, list):
        for item in value:
            if str(item).strip():
                return str(item).strip()
        return ''
    return str(value).strip() if value else ''
