# -*- coding: utf-8 -*-
"""路径解析。

打包成 exe 后，``__file__`` 指向解压出来的临时目录，用户数据不能写在那里
（进程退出就没了）。所以资源与数据要分开：

* 只读资源（图标）→ ``_MEIPASS/app/resources``
* 可写数据（配置、缓存、日志）→ ``%APPDATA%/ArticleReducer``
"""

import os
import sys
from pathlib import Path

from .. import APP_NAME_EN

#: 源码目录下的 app 包根
PACKAGE_DIR = Path(__file__).resolve().parents[1]


def is_frozen():
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def resource_dir():
    """只读资源目录，打包后位于 exe 内部的解压目录。"""
    if is_frozen():
        return Path(sys._MEIPASS) / 'app' / 'resources'
    return PACKAGE_DIR / 'resources'


def resource_path(*parts):
    return resource_dir().joinpath(*parts)


def data_dir():
    """可写数据目录，跨启动稳定。"""
    if sys.platform == 'win32':
        base = os.getenv('APPDATA')
        root = Path(base) if base else Path.home() / 'AppData' / 'Roaming'
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    else:
        base = os.getenv('XDG_CONFIG_HOME')
        root = Path(base) if base else Path.home() / '.config'

    path = root / APP_NAME_EN
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_path():
    return data_dir() / 'cache.db'


def log_path():
    return data_dir() / 'app.log'
