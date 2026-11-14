# -*- coding: utf-8 -*-
"""文章降重助手。

分层约定：

    app.core    纯 Python，零 Qt 依赖，可被 CLI / Web 复用
    app.infra   路径、配置、密钥、存储
    app.ui      PyQt5 界面层，只做展示与事件转发

依赖方向严格单向：ui → infra → core，core 不反向依赖任何上层。
"""

__version__ = '2.0.0'
__release_date__ = '2026-11-14'

APP_NAME = '文章降重助手'
APP_NAME_EN = 'ArticleReducer'
ORG_NAME = 'ZeroOne'
APP_ID = 'ArticleReducer'

__all__ = [
    '__version__',
    '__release_date__',
    'APP_NAME',
    'APP_NAME_EN',
    'ORG_NAME',
    'APP_ID',
]
