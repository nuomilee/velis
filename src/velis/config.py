from pathlib import Path

APP_CONFIG_DIR = Path.home() / '.ai_desktop_organizer'
AI_SETTINGS_PATH = APP_CONFIG_DIR / 'ai_settings.json'
UI_SETTINGS_PATH = APP_CONFIG_DIR / 'ui_settings.json'

APP_NAME = 'AI Desktop Organizer'
WORKSPACE_FOLDER_NAME = 'AI桌面整理'
GRID_SIZE = 5
BOX_MIN_WIDTH = 220
BOX_MIN_HEIGHT = 180
DEFAULT_BOX_WIDTH = 280
DEFAULT_BOX_HEIGHT = 260

DESKTOP_PATH = Path.home() / 'Desktop'
ORGANIZE_ROOT = DESKTOP_PATH / WORKSPACE_FOLDER_NAME

CATEGORY_ORDER = [
    '文档', '表格数据', '演示文稿', '图片', '视频', '音频',
    '压缩包', '程序快捷方式', '代码开发', '设计素材', '其他'
]

EXTENSION_MAP = {
    '.txt': '文档', '.md': '文档', '.pdf': '文档', '.doc': '文档', '.docx': '文档',
    '.xls': '表格数据', '.xlsx': '表格数据', '.csv': '表格数据',
    '.ppt': '演示文稿', '.pptx': '演示文稿',
    '.jpg': '图片', '.jpeg': '图片', '.png': '图片', '.gif': '图片', '.bmp': '图片', '.webp': '图片', '.svg': '图片',
    '.mp4': '视频', '.mkv': '视频', '.avi': '视频', '.mov': '视频', '.flv': '视频',
    '.mp3': '音频', '.wav': '音频', '.flac': '音频', '.aac': '音频', '.m4a': '音频', '.ogg': '音频',
    '.zip': '压缩包', '.rar': '压缩包', '.7z': '压缩包', '.tar': '压缩包', '.gz': '压缩包',
    '.lnk': '程序快捷方式', '.exe': '程序快捷方式', '.msi': '程序快捷方式', '.bat': '程序快捷方式',
    '.py': '代码开发', '.js': '代码开发', '.ts': '代码开发', '.java': '代码开发', '.cpp': '代码开发', '.c': '代码开发', '.json': '代码开发', '.html': '代码开发', '.css': '代码开发',
    '.psd': '设计素材', '.ai': '设计素材', '.sketch': '设计素材', '.fig': '设计素材', '.xd': '设计素材',
}

KEYWORD_CATEGORY_MAP = {
    '文档': ['方案', '合同', '说明', '文档', '笔记', '论文', '简历', '手册', '报告', '制度'],
    '表格数据': ['报表', '数据', '统计', '名单', '清单', '台账', '库存', '财务', 'excel'],
    '演示文稿': ['汇报', '答辩', '演示', '课件', 'ppt'],
    '图片': ['照片', '图片', '截图', '壁纸', '封面', '海报'],
    '视频': ['视频', '录像', '课程', '电影', '剪辑'],
    '音频': ['音频', '歌曲', '录音', '播客', '语音'],
    '压缩包': ['压缩', '打包', '归档'],
    '程序快捷方式': ['微信', '钉钉', 'chrome', 'edge', '浏览器', '启动', '快捷方式', '软件', '程序', 'steam'],
    '代码开发': ['项目', '源码', '代码', 'script', 'python', 'node', '前端', '后端', 'api', '仓库', '开发'],
    '设计素材': ['设计', 'ui', '原型', '素材', 'icon', '图标', 'ps', 'figma'],
}

CATEGORY_PREFIX_MAP = {
    '文档': 'DOC',
    '表格数据': 'DATA',
    '演示文稿': 'PPT',
    '图片': 'IMG',
    '视频': 'VIDEO',
    '音频': 'AUDIO',
    '压缩包': 'ARCHIVE',
    '程序快捷方式': 'APP',
    '代码开发': 'CODE',
    '设计素材': 'DESIGN',
    '其他': 'MISC',
}
