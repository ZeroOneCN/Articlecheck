# -*- coding: utf-8 -*-
"""主窗口。

相比旧版：

* 启动时直接把配置注入 ``BaiduTranslator``，不必再点一次「测试连接」。
* 降重在 QThread 里跑，界面不假死，且可以中途取消。
* 支持分段输入，换行原样保留。
* 指标如实标为「改动率 / 保留率」，不再冒充查重率。
"""

import webbrowser

from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtGui import QFont, QTextBlockFormat, QTextCursor
from PyQt5.QtWidgets import (QApplication, QComboBox, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMainWindow, QMessageBox,
                             QProgressBar, QPushButton, QTabWidget, QTextEdit,
                             QVBoxLayout, QWidget)

from .. import __version__
from ..core import metrics, pipeline
from ..core.translator import BaiduTranslator
from ..infra.settings import Settings
from .diff_view import DiffView
from .worker import ApiTestWorker, TranslateWorker

INTRO_HTML = """
<p><b>使用步骤</b></p>
<ol>
  <li>填写百度翻译的 APPID / APPKEY，点「保存配置」。配置存到用户目录，下次启动自动加载。</li>
  <li>在右侧粘贴原文，可以用换行分段，段落结构会原样保留。</li>
  <li>选择模式后点「开始降重」，跑的过程中可以随时取消。</li>
</ol>
<p><b>模式说明</b></p>
<ul>
  <li>初级：中 → 英 → 德 → 中</li>
  <li>中级：中 → 英 → 德 → 日 → 葡 → 中</li>
  <li>高级：中 → 英 → 德 → 日 → 葡 → 意 → 波 → 保 → 爱 → 中</li>
</ul>
<p><b>关于额度</b></p>
<p>每跳都会重新翻译全文，消耗的字符额度约为「正文字数 × 跳数」。高级模式 9 跳，3000 字约消耗 27000 字符。</p>
<p><b>关于指标</b></p>
<p>「改动率 / 保留率」是本地按编辑距离算出的文本改动比例，不是知网、维普的查重结果。</p>
"""


class RichTextEdit(QTextEdit):
    """带字数统计、首行缩进、纯文本粘贴的编辑框。"""

    def __init__(self, counter=None, parent=None):
        super().__init__(parent)
        self._counter = counter
        self.setStyleSheet(
            # 先写中文名：部分机器只注册了「宋体」而没有 SimSun 这个别名，
            # 写成 SimSun 会匹配失败并回退到间距难看的默认字体。
            'QTextEdit { font-family: "宋体", "SimSun", "Songti SC", serif; '
            'font-size: 12pt; }'
        )
        self.textChanged.connect(self.update_counter)
        self._apply_indent()

    def _block_format(self):
        fmt = QTextBlockFormat()
        fmt.setAlignment(Qt.AlignJustify)
        # 首行缩进按「两个汉字宽度」算，换字号也不会错位（旧版写死 24 像素）
        fmt.setTextIndent(self.fontMetrics().horizontalAdvance('中') * 2)
        return fmt

    def _apply_indent(self):
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setBlockFormat(self._block_format())

    def update_counter(self):
        if self._counter is None:
            return
        text = self.toPlainText()
        self._counter.setText('字符 {} · 词 {}'.format(len(text), len(text.split())))

    def insertFromMimeData(self, source):
        """粘贴时剥掉外部样式，但保留换行。"""
        if not source.hasText():
            super().insertFromMimeData(source)
            return
        cursor = self.textCursor()
        fmt = self._block_format()
        raw = source.text().replace('\r\n', '\n').replace('\r', '\n')
        for index, line in enumerate(raw.split('\n')):
            if index > 0:
                cursor.insertBlock(fmt)
            cursor.insertText(line.strip())


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.settings = Settings()
        migrated = self.settings.migrate_legacy()

        self.translator = BaiduTranslator(
            self.settings.get_appid(), self.settings.get_appkey()
        )
        self.worker = None
        self.test_worker = None

        self._ui_state = QSettings('ZeroOne', 'ArticleReducer')
        self._last_source = ''
        self._last_result = ''

        self._build_ui()
        self._load_settings()
        self._restore_geometry()
        self._refresh_secret_status()
        self._update_estimate()

        if migrated:
            self._set_status('已从旧版 config.json 迁移配置，原文件已改名为 .bak', ok=True)

    # ── 构建界面 ──────────────────────────────────────────
    def _build_ui(self):
        self.setWindowTitle('文章降重助手 v{}'.format(__version__))
        self.resize(1200, 820)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        root.addWidget(self._build_left_panel(), 1)
        root.addWidget(self._build_right_panel(), 2)

    def _build_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # API 配置
        api_group = QGroupBox('API 配置')
        api_layout = QVBoxLayout(api_group)

        api_layout.addWidget(QLabel('APPID'))
        self.appid_edit = QLineEdit()
        self.appid_edit.setPlaceholderText('纯数字，例如 20250101000000000')
        api_layout.addWidget(self.appid_edit)

        api_layout.addWidget(QLabel('APPKEY'))
        self.appkey_edit = QLineEdit()
        self.appkey_edit.setEchoMode(QLineEdit.Password)
        self.appkey_edit.setPlaceholderText('百度翻译开放平台获取')
        api_layout.addWidget(self.appkey_edit)

        buttons = QHBoxLayout()
        self.save_btn = QPushButton('保存配置')
        self.save_btn.clicked.connect(self.save_config)
        self.test_btn = QPushButton('测试连接')
        self.test_btn.clicked.connect(self.test_connection)
        register_btn = QPushButton('注册账号')
        register_btn.clicked.connect(
            lambda: webbrowser.open('https://fanyi-api.baidu.com/')
        )
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.test_btn)
        buttons.addWidget(register_btn)
        api_layout.addLayout(buttons)

        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        api_layout.addWidget(self.status_label)

        layout.addWidget(api_group)

        # 使用说明
        intro_group = QGroupBox('使用说明')
        intro_layout = QVBoxLayout(intro_group)
        intro = QTextEdit()
        intro.setReadOnly(True)
        intro.setHtml(INTRO_HTML)
        intro.setStyleSheet(
            'QTextEdit { background: #fafafa; border: none; padding: 6px; '
            'font-family: "微软雅黑", "Microsoft YaHei", sans-serif; '
            'font-size: 12px; }'
        )
        intro_layout.addWidget(intro)
        layout.addWidget(intro_group, 1)

        return panel

    def _build_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        header = QHBoxLayout()
        self.metrics_label = QLabel('尚未计算')
        self.metrics_label.setStyleSheet('font-size: 14px; font-weight: bold;')
        hint = QLabel('（本地估算的文本改动比例，不是查重报告）')
        hint.setStyleSheet('color: #888; font-size: 11px;')
        header.addWidget(self.metrics_label)
        header.addWidget(hint)
        header.addStretch()
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_edit_tab(), '编辑')
        self.diff_view = DiffView()
        self.tabs.addTab(self.diff_view, '对比')
        layout.addWidget(self.tabs, 1)

        return panel

    def _build_edit_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        # 输入
        input_group = QGroupBox('原文输入')
        input_layout = QVBoxLayout(input_group)

        input_header = QHBoxLayout()
        input_header.addStretch()
        paste_btn = QPushButton('一键粘贴')
        paste_btn.clicked.connect(self.paste_text)
        input_header.addWidget(paste_btn)
        self.input_counter = QLabel('字符 0 · 词 0')
        self.input_counter.setStyleSheet('color: #888;')
        input_header.addWidget(self.input_counter)
        input_layout.addLayout(input_header)

        self.input_text = RichTextEdit(counter=self.input_counter)
        self.input_text.setPlaceholderText('粘贴需要降重的文章，可用换行分段…')
        self.input_text.setMinimumHeight(180)
        self.input_text.textChanged.connect(self._schedule_estimate)
        input_layout.addWidget(self.input_text)
        layout.addWidget(input_group, 1)

        # 控制区
        controls = QHBoxLayout()
        controls.addWidget(QLabel('降重模式'))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(list(pipeline.MODES.keys()))
        self.mode_combo.currentTextChanged.connect(self._update_estimate)
        controls.addWidget(self.mode_combo)

        self.start_btn = QPushButton('开始降重')
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(self.start_translate)
        controls.addWidget(self.start_btn)

        self.cancel_btn = QPushButton('取消')
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_translate)
        controls.addWidget(self.cancel_btn)
        controls.addStretch()
        layout.addLayout(controls)

        self.estimate_label = QLabel('')
        self.estimate_label.setStyleSheet('color: #666; font-size: 11px;')
        layout.addWidget(self.estimate_label)

        self.progress = QProgressBar()
        self.progress.setAlignment(Qt.AlignCenter)
        self.progress.setFormat('%p%')
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # 进度明细单独一行，避免塞进进度条被截断
        self.progress_label = QLabel('')
        self.progress_label.setStyleSheet('color: #666; font-size: 11px;')
        layout.addWidget(self.progress_label)

        # 输出
        output_group = QGroupBox('降重结果')
        output_layout = QVBoxLayout(output_group)

        output_header = QHBoxLayout()
        output_header.addStretch()
        copy_btn = QPushButton('一键复制')
        copy_btn.clicked.connect(self.copy_text)
        output_header.addWidget(copy_btn)
        self.output_counter = QLabel('字符 0 · 词 0')
        self.output_counter.setStyleSheet('color: #888;')
        output_header.addWidget(self.output_counter)
        output_layout.addLayout(output_header)

        self.output_text = RichTextEdit(counter=self.output_counter)
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText('降重结果会显示在这里…')
        self.output_text.setMinimumHeight(180)
        output_layout.addWidget(self.output_text)
        layout.addWidget(output_group, 1)

        return page

    # ── 配置 ──────────────────────────────────────────────
    def _load_settings(self):
        self.appid_edit.setText(self.settings.get_appid())
        self.appkey_edit.setText(self.settings.get_appkey())

        mode = self.settings.get_mode()
        index = self.mode_combo.findText(mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)

        if not self.settings.has_credentials():
            self._set_status('尚未配置凭证，点「注册账号」获取 APPID / APPKEY。', ok=False)

    def _refresh_secret_status(self):
        from ..infra import secret_store
        backend = secret_store.backend_name()
        if backend == 'keyring':
            self._set_status('密钥存储：系统凭据管理器（已加密）', ok=True)
        elif backend == 'dpapi':
            self._set_status('密钥存储：Windows DPAPI（绑定当前账户）', ok=True)
        else:
            self._set_status(
                '密钥存储：未加密（仅 base64 混淆）。建议 pip install keyring。',
                ok=False,
            )

    def _set_status(self, text, ok=True):
        color = '#1a7f37' if ok else '#b54708'
        self.status_label.setText(
            '<span style="color:{};">{}</span>'.format(color, text)
        )

    def save_config(self):
        if not self._sync_credentials(show_error=True):
            return
        self._refresh_secret_status()
        QMessageBox.information(self, '已保存', '配置已保存，下次启动自动加载。')

    def _sync_credentials(self, show_error=False):
        appid = self.appid_edit.text().strip()
        appkey = self.appkey_edit.text().strip()

        if not appid or not appkey:
            if show_error:
                QMessageBox.warning(self, '缺少配置', '请填写 APPID 和 APPKEY。')
            return False

        if (appid != self.settings.get_appid()
                or appkey != self.settings.get_appkey()):
            self.settings.set_credentials(appid, appkey)

        self.translator.update_credentials(appid, appkey)
        return True

    def test_connection(self):
        if self.test_worker is not None and self.test_worker.isRunning():
            return
        if not self._sync_credentials(show_error=True):
            return

        answer = QMessageBox.question(
            self, '测试连接',
            '测试会真实调用一次百度翻译接口，消耗约 10 个字符额度。\n继续吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return

        self.test_btn.setEnabled(False)
        self._set_status('正在测试连接…')

        self.test_worker = ApiTestWorker(self.translator, self)
        self.test_worker.succeeded.connect(self._on_test_ok)
        self.test_worker.failed.connect(self._on_test_failed)
        self.test_worker.finished.connect(lambda: self.test_btn.setEnabled(True))
        self.test_worker.start()

    def _on_test_ok(self, result):
        self._set_status('API 验证成功：测试连接 → {}'.format(result), ok=True)
        QMessageBox.information(self, '成功', 'API 连接正常。')

    def _on_test_failed(self, message):
        self._set_status('API 验证失败：{}'.format(message), ok=False)
        QMessageBox.warning(self, '验证失败', message)

    # ── 额度预估 ──────────────────────────────────────────
    def _schedule_estimate(self):
        if not hasattr(self, '_estimate_timer'):
            self._estimate_timer = QTimer(self)
            self._estimate_timer.setSingleShot(True)
            self._estimate_timer.setInterval(400)
            self._estimate_timer.timeout.connect(self._update_estimate)
        self._estimate_timer.start()

    def _update_estimate(self):
        text = self.input_text.toPlainText() if hasattr(self, 'input_text') else ''
        if not text.strip():
            self.estimate_label.setText('')
            return

        mode = self.mode_combo.currentText() if hasattr(self, 'mode_combo') else '初级'
        hops = len(pipeline.MODES.get(mode, ['zh', 'zh'])) - 1
        calls = pipeline.estimate_requests(text, mode)
        chars = len(text) * hops
        self.estimate_label.setText(
            '预计 {} 次请求 · 约消耗 {} 字符额度（{} 跳）'.format(calls, chars, hops)
        )

    # ── 降重 ──────────────────────────────────────────────
    def start_translate(self):
        if self.worker is not None and self.worker.isRunning():
            return

        text = self.input_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, '没有内容', '请先输入需要降重的文章。')
            return

        if not self._sync_credentials(show_error=True):
            return

        mode = self.mode_combo.currentText()
        self.settings.set_mode(mode)

        hops = len(pipeline.MODES[mode]) - 1
        estimate = len(text) * hops
        if estimate > 40000:
            answer = QMessageBox.question(
                self, '额度提醒',
                '本次预计消耗约 {} 字符额度（{} 跳 × {} 字）。\n确定继续吗？'.format(
                    estimate, hops, len(text)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        self._last_source = text
        self.output_text.clear()
        self.output_text.update_counter()
        self.progress.setValue(0)
        self.metrics_label.setText('计算中…')
        self._set_busy(True)

        self.worker = TranslateWorker(self.translator, text, mode, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.succeeded.connect(self._on_success)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.start()

    def cancel_translate(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self._set_status('正在取消…')

    def _set_busy(self, busy):
        self.start_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.mode_combo.setEnabled(not busy)
        self.save_btn.setEnabled(not busy)
        self.test_btn.setEnabled(not busy)

    def _on_progress(self, percent, message):
        self.progress.setValue(percent)
        self.progress_label.setText(message)

    def _on_success(self, result, report):
        self._set_busy(False)
        self._last_result = result
        self.output_text.setPlainText(result)
        self.output_text.update_counter()
        self.progress.setValue(100)
        self.progress_label.setText('完成')
        self.metrics_label.setText(metrics.format_report(report))
        self.diff_view.show_diff(self._last_source, result)
        self._set_status('降重完成。', ok=True)

    def _on_failed(self, message):
        self._set_busy(False)
        self.progress.setValue(0)
        self.progress_label.setText('')
        self.metrics_label.setText('未完成')
        self._set_status('失败：{}'.format(message), ok=False)
        QMessageBox.warning(self, '降重失败', message)

    def _on_cancelled(self):
        self._set_busy(False)
        self.progress.setValue(0)
        self.progress_label.setText('已取消')
        self.metrics_label.setText('已取消')
        self._set_status('已取消。', ok=False)

    # ── 剪贴板 ────────────────────────────────────────────
    def paste_text(self):
        text = QApplication.clipboard().text()
        if text:
            self.input_text.setPlainText(text)
            self.input_text._apply_indent()
            self._update_estimate()

    def copy_text(self):
        text = self.output_text.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._set_status('已复制到剪贴板。', ok=True)

    # ── 窗口状态 ──────────────────────────────────────────
    def _restore_geometry(self):
        geometry = self._ui_state.value('window/geometry')
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        self._ui_state.setValue('window/geometry', self.saveGeometry())

        for thread in (self.worker, self.test_worker):
            if thread is not None and thread.isRunning():
                if hasattr(thread, 'cancel'):
                    thread.cancel()
                thread.quit()
                thread.wait(3000)
        super().closeEvent(event)


def main():
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName('ArticleReducer')

    # 界面统一用无衬线中文字体；正文编辑框另外指定宋体（论文习惯）
    ui_font = QFont()
    ui_font.setFamilies(['微软雅黑', 'Microsoft YaHei', 'Segoe UI', 'sans-serif'])
    ui_font.setPointSize(9)
    app.setFont(ui_font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
