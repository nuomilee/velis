import tempfile
import unittest
from pathlib import Path

from src.ai_desktop_organizer.utils import clean_filename, ensure_unique_path


class UtilsTests(unittest.TestCase):
    def test_clean_filename(self):
        self.assertEqual(clean_filename(' 项目: 方案*最终版? '), '项目_方案_最终版')

    def test_ensure_unique_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'a.txt'
            base.write_text('1', encoding='utf-8')
            unique = ensure_unique_path(base)
            self.assertEqual(unique.name, 'a_1.txt')


if __name__ == '__main__':
    unittest.main()
