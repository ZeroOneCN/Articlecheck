# -*- coding: utf-8 -*-
"""翻译结果缓存。

翻译链每跳都要重发全文，一篇 3000 字的文章跑高级模式就是 27000 字符额度。
而这些额度里绝大部分是重复的：调一次参数重跑、改个错别字重跑、上次跑到一半
取消再跑——命中缓存就能直接省下来。

用 ``sqlite3``（标准库，无需额外依赖）存在用户数据目录，键为
``版本 + 源语言 + 目标语言 + 原文`` 的 SHA-256。

缓存只影响「同一个句子重复翻译」这一种情况，不影响结果正确性：
命中时返回的就是上次同样的输入得到的同样输出。
"""

import hashlib
import sqlite3
import threading
import time
from pathlib import Path

from . import paths

#: 缓存格式版本。保护逻辑或链路语义变化时递增，旧缓存自动失效。
SCHEMA_VERSION = 'v1'

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    key        TEXT PRIMARY KEY,
    src        TEXT NOT NULL,
    dst        TEXT NOT NULL,
    source     TEXT NOT NULL,
    target     TEXT NOT NULL,
    created    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_created ON translations (created);
"""


class TranslationCache:
    """线程安全的键值缓存。连接按线程懒创建。"""

    def __init__(self, path=None, enabled=True):
        self.path = Path(path) if path else paths.cache_path()
        self.enabled = enabled
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

    # ── 连接 ──────────────────────────────────────────────
    def _connect(self):
        connection = getattr(self._local, 'conn', None)
        if connection is None:
            connection = sqlite3.connect(str(self.path), timeout=5)
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA synchronous=NORMAL')
            self._local.conn = connection
        return connection

    def _init_db(self):
        try:
            with self._lock:
                self._connect().executescript(_SCHEMA)
        except sqlite3.Error:
            # 缓存坏了不该拖累主流程，退化成「不缓存」
            self.enabled = False

    # ── 键 ────────────────────────────────────────────────
    @staticmethod
    def make_key(text, src, dst):
        raw = '{}\x00{}\x00{}\x00{}'.format(SCHEMA_VERSION, src, dst, text)
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    # ── 读写 ──────────────────────────────────────────────
    def get(self, text, src, dst):
        if not self.enabled:
            return None
        key = self.make_key(text, src, dst)
        try:
            row = self._connect().execute(
                'SELECT target FROM translations WHERE key = ?', (key,)
            ).fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def put(self, text, src, dst, translated):
        if not self.enabled or not translated:
            return
        key = self.make_key(text, src, dst)
        try:
            with self._lock:
                self._connect().execute(
                    'INSERT OR REPLACE INTO translations'
                    ' (key, src, dst, source, target, created)'
                    ' VALUES (?, ?, ?, ?, ?, ?)',
                    (key, src, dst, text, translated, time.time()),
                )
                self._connect().commit()
        except sqlite3.Error:
            pass

    # ── 维护 ──────────────────────────────────────────────
    def stats(self):
        """返回 ``(条目数, 占用字节数)``。"""
        try:
            count = self._connect().execute(
                'SELECT COUNT(*) FROM translations'
            ).fetchone()[0]
        except sqlite3.Error:
            return 0, 0
        size = self.path.stat().st_size if self.path.exists() else 0
        for suffix in ('-wal', '-shm'):
            extra = self.path.with_name(self.path.name + suffix)
            if extra.exists():
                size += extra.stat().st_size
        return count, size

    def clear(self):
        """清空缓存，返回被清除的条目数。"""
        try:
            with self._lock:
                count = self._connect().execute(
                    'SELECT COUNT(*) FROM translations'
                ).fetchone()[0]
                self._connect().execute('DELETE FROM translations')
                self._connect().commit()
                self._connect().execute('VACUUM')
            return count
        except sqlite3.Error:
            return 0

    def prune(self, keep_days=90):
        """删除超过保留期的条目，避免缓存无限增长。"""
        if not self.enabled:
            return 0
        cutoff = time.time() - keep_days * 86400
        try:
            with self._lock:
                cursor = self._connect().execute(
                    'DELETE FROM translations WHERE created < ?', (cutoff,)
                )
                self._connect().commit()
                return cursor.rowcount or 0
        except sqlite3.Error:
            return 0
