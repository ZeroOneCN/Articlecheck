# -*- coding: utf-8 -*-
"""统一异常类型。

重构前，所有失败都以「含『错误』二字的字符串」形式返回，调用方靠
``'错误' in result`` 来猜。结果是：一篇讨论「错误处理机制」的论文，
翻译得再正确也会被判为失败。

现在改成抛异常，调用方只处理成功路径。
"""


class AppError(Exception):
    """本项目所有异常的基类。"""

    def __init__(self, message, *, code=None, retryable=False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable

    def __str__(self):
        return self.message


class ConfigError(AppError):
    """配置缺失、格式不对或读写失败。"""


class TranslationError(AppError):
    """翻译服务返回错误，或网络请求失败。"""


class Cancelled(AppError):
    """用户主动取消。"""
