# -*- coding: utf-8 -*-
"""后台任务线程。

v1 把整条降重链路跑在主线程里，靠 ``QApplication.processEvents()`` 硬撑，
结果是窗口假死 + 可重入。现在搬进 QThread，主线程只处理信号。
"""

import traceback

from PyQt5.QtCore import QThread, pyqtSignal

from . import metrics, pipeline
from .errors import AppError, Cancelled


class TranslateWorker(QThread):
    """执行一次完整的降重链路。"""

    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(str, dict, dict)
    failed = pyqtSignal(str, str)
    cancelled = pyqtSignal()

    def __init__(self, translator, text, mode, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._text = text
        self._mode = mode
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def is_cancelled(self):
        return self._cancel

    def _on_progress(self, hop, hops, para_index, para_total,
                     seg_index, seg_total, from_lang, to_lang):
        percent = pipeline.percentage(hop, hops, para_index, para_total,
                                      seg_index, seg_total)
        message = '{} → {} · 第 {}/{} 段 · 第 {}/{} 跳'.format(
            pipeline.lang_label(from_lang), pipeline.lang_label(to_lang),
            para_index + 1, para_total, hop + 1, hops)
        self.progress.emit(percent, message)

    def run(self):
        self._translator.should_cancel = self.is_cancelled
        self._translator.stats.reset()
        try:
            result = pipeline.run(
                self._text, self._mode, self._translator,
                progress=self._on_progress,
                should_cancel=self.is_cancelled,
            )
            if self._cancel:
                self.cancelled.emit()
                return
            report = metrics.compare(self._text, result)
            self.succeeded.emit(result, report, self._translator.stats.as_dict())
        except Cancelled:
            self.cancelled.emit()
        except AppError as exc:
            self.failed.emit(str(exc), '')
        except Exception as exc:                        # 兜底，不让线程静默死掉
            self.failed.emit(
                '未预期的错误：{}: {}'.format(type(exc).__name__, exc),
                traceback.format_exc(),
            )
        finally:
            self._translator.should_cancel = None


class ApiTestWorker(QThread):
    """连通性测试。单独开线程，避免 20 秒超时把窗口冻住。"""

    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._translator = translator

    def run(self):
        try:
            # 测试必须走网络，命中的缓存证明不了凭证有效
            result = self._translator.translate(
                '测试连接', 'zh', 'en', use_cache=False, use_protect=False
            )
            self.succeeded.emit(result)
        except AppError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit('{}: {}'.format(type(exc).__name__, exc))
