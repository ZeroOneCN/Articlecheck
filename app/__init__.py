# -*- coding: utf-8 -*-
"""文章降重助手。

目录只有一个代码包 ``app``，模块按职责命名，不再分子包：

    paths / settings / secret_store   环境与配置
    segmenter / protect / translator  翻译链路的三块基石
    pipeline / metrics / cache        编排、度量、缓存
    export                            结果导出
    theme / widgets / *_view / worker 界面

依赖方向保持单向：界面模块 → 业务模块 → 标准库，业务模块不导入 PyQt。
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
