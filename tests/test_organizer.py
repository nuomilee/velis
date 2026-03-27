import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.velis.ai_classifier import AIResult, AISettings
from src.velis.organizer import DesktopOrganizer


class OrganizerTests(unittest.TestCase):
    def test_classify_file_by_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / '报告.docx'
            p.write_text('x', encoding='utf-8')
            organizer = DesktopOrganizer(Path(tmp), Path(tmp) / 'out', AISettings(enabled=False))
            category, reason, resolved_target, ai_summary, ai_result = organizer.classify_file(p)
            self.assertEqual(category, '文档')
            self.assertIn('扩展名', reason)
            self.assertIsNone(resolved_target)
            self.assertEqual(ai_summary, '')
            self.assertIsNone(ai_result)

    def test_classify_lnk_by_real_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / '微信 快捷方式.lnk'
            p.write_text('x', encoding='utf-8')
            organizer = DesktopOrganizer(Path(tmp), Path(tmp) / 'out', AISettings(enabled=False))
            with patch('src.velis.organizer.resolve_windows_shortcut', return_value=Path(r'C:\Program Files\WeChat\WeChat.exe')):
                category, reason, resolved_target, _, _ = organizer.classify_file(p)
            self.assertEqual(category, '程序快捷方式')
            self.assertEqual(resolved_target, Path(r'C:\Program Files\WeChat\WeChat.exe'))
            self.assertIn('快捷方式真实目标', reason)

    def test_organize_moves_files_in_rule_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            desktop = Path(tmp) / 'desktop'
            out = desktop / '拾叶'
            desktop.mkdir(parents=True, exist_ok=True)
            file1 = desktop / '项目方案.docx'
            file2 = desktop / '财务数据.xlsx'
            file3 = desktop / '微信 快捷方式.lnk'
            file1.write_text('a', encoding='utf-8')
            file2.write_text('b', encoding='utf-8')
            file3.write_text('c', encoding='utf-8')

            organizer = DesktopOrganizer(desktop, out, AISettings(enabled=False))

            def fake_resolve(path: Path):
                if path.suffix.lower() == '.lnk':
                    return Path(r'C:\Program Files\WeChat\WeChat.exe')
                return None

            with patch('src.velis.organizer.resolve_windows_shortcut', side_effect=fake_resolve):
                records = organizer.organize()

            self.assertEqual(len(records), 3)
            self.assertTrue(any(r.category == '文档' for r in records))
            self.assertTrue(any(r.category == '表格数据' for r in records))
            self.assertTrue(any(r.category == '程序快捷方式' for r in records))
            self.assertTrue(all(r.target_path.exists() for r in records))
            self.assertFalse(file1.exists())
            self.assertFalse(file2.exists())
            self.assertFalse(file3.exists())
            self.assertTrue(all(not r.renamed_by_ai for r in records))

    def test_ai_mode_skips_rename_when_ai_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            desktop = Path(tmp) / 'desktop'
            out = desktop / '拾叶'
            desktop.mkdir(parents=True, exist_ok=True)
            file1 = desktop / '三国恋 - 小野来了.flac'
            file1.write_text('a', encoding='utf-8')

            organizer = DesktopOrganizer(desktop, out, AISettings(enabled=True))
            with patch.object(organizer.ai_classifier, 'analyze', side_effect=RuntimeError('连接失败')):
                records = organizer.organize()

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].new_name, '(未重命名)')
            self.assertTrue(file1.exists())
            self.assertFalse(records[0].renamed_by_ai)
            self.assertIn('跳过原因', records[0].classification_reason)

    def test_ai_mode_uses_ai_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            desktop = Path(tmp) / 'desktop'
            out = desktop / '拾叶'
            desktop.mkdir(parents=True, exist_ok=True)
            file1 = desktop / '三国恋 - 小野来了.flac'
            file1.write_text('a', encoding='utf-8')

            organizer = DesktopOrganizer(desktop, out, AISettings(enabled=True))
            fake_ai = AIResult(
                provider='local-openai-compatible',
                mode='local',
                model='qwen3:5:2b',
                summary='识别为歌曲名与歌手名',
                tags=['歌曲'],
                suggested_category='音频',
                suggested_name='三国恋-小野来了',
                raw='{}',
            )
            with patch.object(organizer.ai_classifier, 'analyze', return_value=fake_ai):
                records = organizer.organize()

            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].renamed_by_ai)
            self.assertEqual(records[0].new_name, '三国恋-小野来了.flac')
            self.assertTrue((out / '音频' / '三国恋-小野来了.flac').exists())
            self.assertFalse(file1.exists())


if __name__ == '__main__':
    unittest.main()
