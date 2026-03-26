import shutil
from pathlib import Path
from typing import Iterable, List, Tuple

from .ai_classifier import AIClassifier, AIResult, AISettings
from .config import CATEGORY_ORDER, CATEGORY_PREFIX_MAP, EXTENSION_MAP, KEYWORD_CATEGORY_MAP, ORGANIZE_ROOT, WORKSPACE_FOLDER_NAME
from .models import FileRecord
from .utils import clean_filename, ensure_unique_path, read_audio_metadata, resolve_windows_shortcut


class DesktopOrganizer:
    def __init__(self, desktop_path: Path, organize_root: Path | None = None, ai_settings: AISettings | None = None):
        self.desktop_path = desktop_path
        self.organize_root = organize_root or ORGANIZE_ROOT
        self.ai_settings = ai_settings or AISettings()
        self.ai_classifier = AIClassifier(self.ai_settings)

    def scan_files(self) -> List[Path]:
        files = []
        for item in self.desktop_path.iterdir():
            if item.name == WORKSPACE_FOLDER_NAME:
                continue
            if item.is_file():
                files.append(item)
        return files

    def classify_file(self, file_path: Path) -> Tuple[str, str, Path | None, str, AIResult | None]:
        suffix = file_path.suffix.lower()
        resolved_target = resolve_windows_shortcut(file_path)
        analysis_target = resolved_target or file_path
        analysis_suffix = analysis_target.suffix.lower()
        default_category = EXTENSION_MAP.get(analysis_suffix)
        name_lower = analysis_target.stem.lower()

        if analysis_suffix == '.lnk' or default_category is None:
            keyword_category = self._classify_by_keywords(name_lower)
            if keyword_category:
                category = keyword_category
                reason = '根据文件名关键词判断'
            else:
                category = default_category or '其他'
                reason = '未命中扩展名与关键词规则'
        else:
            keyword_category = self._classify_by_keywords(name_lower)
            if keyword_category:
                category = keyword_category
                reason = '根据文件名关键词覆盖扩展名分类'
            else:
                category = default_category
                reason = '根据扩展名分类'

        ai_summary = ''
        ai_result: AIResult | None = None
        if self.ai_settings.enabled:
            try:
                ai_result = self.ai_classifier.analyze(
                    file_name=file_path.name,
                    final_name=analysis_target.name,
                    file_suffix=suffix,
                    final_suffix=analysis_suffix,
                    rule_category=category,
                    rule_reason=reason,
                    is_shortcut=suffix == '.lnk',
                    shortcut_target=str(resolved_target) if resolved_target else None,
                )
                ai_summary = ai_result.summary
                if ai_result.suggested_category and ai_result.suggested_category in CATEGORY_PREFIX_MAP:
                    category = ai_result.suggested_category
                    reason = f"AI分析分类：{ai_result.summary or 'AI已返回分类结果'}"
                else:
                    reason = f"规则分类；AI补充：{ai_result.summary}" if ai_result.summary else reason
            except Exception as exc:
                ai_summary = f"AI分析失败：{exc}"
                reason = f"{reason}；{ai_summary}"

        if resolved_target:
            reason = f"快捷方式真实目标：{resolved_target}；{reason}"

        return category, reason, resolved_target, ai_summary, ai_result

    def _classify_by_keywords(self, name_lower: str) -> str | None:
        for category, keywords in KEYWORD_CATEGORY_MAP.items():
            for keyword in keywords:
                if keyword.lower() in name_lower:
                    return category
        return None

    def generate_new_name(self, file_path: Path, category: str, ai_result: AIResult | None) -> tuple[str, bool, str]:
        metadata = read_audio_metadata(file_path) if category == '音频' else {}
        if metadata.get('title') and metadata.get('artist'):
            suggested_name = clean_filename(f"{metadata['title']} - {metadata['artist']}")
            return f"{suggested_name}{file_path.suffix.lower()}", True, '音频元数据'

        if self.ai_settings.enabled:
            if ai_result is None:
                raise RuntimeError('AI 未返回结果，已跳过重命名')
            suggested_name = clean_filename(ai_result.suggested_name)
            if not suggested_name:
                raise RuntimeError('AI 未返回有效文件名，已跳过重命名')
            return f"{suggested_name}{file_path.suffix.lower()}", True, 'AI'

        prefix = CATEGORY_PREFIX_MAP.get(category, CATEGORY_PREFIX_MAP['其他'])
        cleaned = clean_filename(file_path.stem)
        return f"{prefix}_{cleaned}{file_path.suffix.lower()}", False, '规则'

    def organize(self) -> List[FileRecord]:
        self.organize_root.mkdir(parents=True, exist_ok=True)
        records: List[FileRecord] = []

        for file_path in self.scan_files():
            category, reason, resolved_target, ai_summary, ai_result = self.classify_file(file_path)
            target_dir = self.organize_root / category
            target_dir.mkdir(parents=True, exist_ok=True)

            try:
                new_name, renamed_by_ai, source_kind = self.generate_new_name(file_path, category, ai_result)
            except Exception as exc:
                records.append(
                    FileRecord(
                        original_path=file_path,
                        category=category,
                        new_name='(未重命名)',
                        target_path=file_path,
                        resolved_target_path=resolved_target,
                        classification_reason=f"{reason}；跳过原因：{exc}",
                        ai_summary=ai_summary,
                        renamed_by_ai=False,
                    )
                )
                continue

            if source_kind == '音频元数据':
                reason = f"{reason}；命名来源：音频文件属性"
            elif source_kind == 'AI':
                reason = f"{reason}；命名来源：AI"
            else:
                reason = f"{reason}；命名来源：规则"

            target_path = ensure_unique_path(target_dir / new_name)
            shutil.move(str(file_path), str(target_path))

            records.append(
                FileRecord(
                    original_path=file_path,
                    category=category,
                    new_name=target_path.name,
                    target_path=target_path,
                    resolved_target_path=resolved_target,
                    classification_reason=reason,
                    ai_summary=ai_summary,
                    renamed_by_ai=renamed_by_ai,
                )
            )

        return records

    def category_files(self, category: str) -> Iterable[Path]:
        directory = self.organize_root / category
        if not directory.exists():
            return []
        return sorted([p for p in directory.iterdir() if p.is_file()], key=lambda p: p.name.lower())

    def existing_categories(self) -> List[str]:
        categories = [name for name in CATEGORY_ORDER if (self.organize_root / name).exists()]
        for item in self.organize_root.iterdir() if self.organize_root.exists() else []:
            if item.is_dir() and item.name not in categories:
                categories.append(item.name)
        return categories
