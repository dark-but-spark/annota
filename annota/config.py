"""Annota 配置常量"""

import os
import platform
from pathlib import Path

# ── Zotero 数据路径（自动适配 Windows / macOS / Linux）──────────────
def _default_zotero_dir() -> str:
    system = platform.system()
    if system == "Darwin":  # macOS
        return str(Path.home() / "Zotero")
    elif system == "Linux":
        return str(Path.home() / "Zotero")
    else:  # Windows
        return r"C:\Users\username\Zotero"

ZOTERO_DATA_DIR = Path(os.environ.get(
    "ZOTERO_DATA_DIR",
    _default_zotero_dir()
))
ZOTERO_DB_PATH = ZOTERO_DATA_DIR / "zotero.sqlite"
ZOTERO_STORAGE_DIR = ZOTERO_DATA_DIR / "storage"

# ── Zotero 数据库常量 ────────────────────────────────────────────
LIBRARY_ID = 1  # 用户本地库

# itemTypeID 映射
ITEM_TYPE_ANNOTATION = 1
ITEM_TYPE_ATTACHMENT = 3
ITEM_TYPE_NOTE = 28

# 批注类型 (itemAnnotations.type)
ANN_HIGHLIGHT = 1
ANN_NOTE = 2
ANN_IMAGE = 3
ANN_INK = 4
ANN_UNDERLINE = 5
ANN_TEXT = 6

ANN_TYPE_MAP = {
    "highlight": ANN_HIGHLIGHT,
    "note": ANN_NOTE,
    "image": ANN_IMAGE,
    "ink": ANN_INK,
    "underline": ANN_UNDERLINE,
    "text": ANN_TEXT,
}

# Zotero key 生成字符集 (8字符)
KEY_CHARSET = "23456789ABCDEFGHIJKLMNPQRSTUVWXYZ"
KEY_LENGTH = 8

# 默认批注颜色
DEFAULT_COLOR = "#ffd400"

# ── SQLite 连接与重试配置 ───────────────────────────────────────
DB_TIMEOUT = 30           # SQLite 连接超时（秒）
DB_RETRY_COUNT = 3        # 锁冲突最大重试次数
DB_RETRY_BASE_DELAY = 1   # 指数退避基础延迟（秒）

# Optional Ollama local preprocessor. An empty model disables model calls.
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_LLM_MODEL = os.environ.get("OLLAMA_LLM_MODEL", "qwen2.5:7b")
OLLAMA_LLM_FALLBACK_MODEL = os.environ.get(
    "OLLAMA_LLM_FALLBACK_MODEL", "deepseek-r1:1.5b"
)
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "90"))
OLLAMA_AUTO_START = os.environ.get("OLLAMA_AUTO_START", "1").lower() not in {
    "0",
    "false",
    "no",
}

# ── Paper translation ───────────────────────────────────────────
TRANSLATION_TARGET_LANGUAGE = os.environ.get("ANNOTA_TRANSLATION_TARGET", "zh-CN")
TRANSLATION_CHUNK_CHARS = int(os.environ.get("ANNOTA_TRANSLATION_CHUNK_CHARS", "3000"))
TRANSLATION_PROVIDER = os.environ.get("ANNOTA_TRANSLATION_PROVIDER", "auto").lower()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get(
    "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
).rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TIMEOUT = float(os.environ.get("DEEPSEEK_TIMEOUT", "120"))

ANNOTA_USER_CONFIG_PATH = Path(
    os.environ.get("ANNOTA_CONFIG_PATH", str(Path.home() / ".annota" / "config.json"))
)
