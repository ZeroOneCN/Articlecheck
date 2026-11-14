# -*- coding: utf-8 -*-
"""配置持久化。

旧版有三个毛病：

* 用相对路径 ``'config.json'``，从别的目录启动就找不到配置——「配置凭空消失」。
* 配置写两份盘：``ConfigManager`` 写 JSON，``APIConfigDialog`` 写 QSettings，
  两个真相来源，且那个对话框从来没被打开过。
* 重启后只把 appid/appkey 塞进输入框，没注入给 ``TranslationAPI``，
  于是用户必须点一次「测试连接」（还顺带消耗额度）才能用。

现在：单一 JSON 存在用户目录，APPKEY 交给 ``secret_store``。
"""

import json
import sys
from pathlib import Path

from . import paths, secret_store

APP_NAME = 'ArticleReducer'
CONFIG_FILENAME = 'settings.json'

DEFAULT_MODE = '初级'


def config_dir():
    """用户级配置目录，跨启动稳定。"""
    return paths.data_dir()


def config_path():
    return config_dir() / CONFIG_FILENAME


def legacy_config_candidates():
    """旧版可能把 config.json 落在这些地方。"""
    candidates = [Path.cwd() / 'config.json',
                  paths.PACKAGE_DIR.parent / 'config.json']
    if getattr(sys, 'frozen', False):
        candidates.insert(0, Path(sys.executable).resolve().parent / 'config.json')
    return candidates


class Settings:
    """读写配置。非密钥项进 JSON，密钥进 secret_store。"""

    def __init__(self):
        self._data = self._load()
        self.secret_backend = secret_store.backend_name()

    # ── 读写 ──────────────────────────────────────────────
    def _load(self):
        path = config_path()
        if not path.exists():
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _flush(self):
        path = config_path()
        tmp = path.with_suffix('.tmp')
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        tmp.replace(path)

    # ── 迁移 ──────────────────────────────────────────────
    def migrate_legacy(self):
        """把旧版明文 config.json 搬进新位置，然后给原文件加 .bak。

        Returns:
            bool 是否发生了迁移
        """
        if self._data.get('appid') and self.get_appkey():
            return False

        for candidate in legacy_config_candidates():
            if not candidate.exists():
                continue
            try:
                with open(candidate, 'r', encoding='utf-8') as handle:
                    legacy = json.load(handle)
            except (OSError, ValueError):
                continue

            appid = str(legacy.get('appid', '')).strip()
            appkey = str(legacy.get('appkey', '')).strip()
            if not (appid or appkey):
                continue

            self._data['appid'] = appid
            self._flush()
            if appkey:
                secret_store.save_secret(appkey)

            try:
                candidate.replace(candidate.with_suffix('.json.bak'))
            except OSError:
                pass
            return True

        return False

    # ── 凭证 ──────────────────────────────────────────────
    def get_appid(self):
        return str(self._data.get('appid', ''))

    def get_appkey(self):
        return secret_store.load_secret()

    def has_credentials(self):
        return bool(self.get_appid() and self.get_appkey())

    def set_credentials(self, appid, appkey):
        self._data['appid'] = (appid or '').strip()
        self._flush()
        self.secret_backend = secret_store.save_secret((appkey or '').strip())

    # ── 普通偏好 ──────────────────────────────────────────
    def get_mode(self):
        return str(self._data.get('mode', DEFAULT_MODE))

    def set_mode(self, mode):
        self._data['mode'] = mode
        self._flush()

    def cache_enabled(self):
        """结果缓存开关。默认开启，省额度是主要收益。"""
        return bool(self._data.get('cache_enabled', True))

    def set_cache_enabled(self, enabled):
        self._data['cache_enabled'] = bool(enabled)
        self._flush()

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self._flush()
