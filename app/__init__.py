# -*- coding: utf-8 -*-
"""文章降重助手。

分层约定：
    app.core    纯 Python，零 Qt 依赖，可被 CLI / Web 复用
    app.infra   配置、密钥、存储
    app.ui      PyQt5 界面层，只做展示与事件转发
"""

__version__ = '2.0.0'
__all__ = ['__version__']
