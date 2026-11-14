# -*- coding: utf-8 -*-
"""主窗口。

布局思路：左侧固定侧栏放「配置 / 步骤 / 额度」，右侧放「正文工作区」。
所有内容都在白卡片里，页面底色只有一种，不再出现 v1 那种灰白灰三层嵌套。

与 v1 的行为差异：

* 启动时直接把配置注入 ``BaiduTranslator``，不必再点一次「测试连接」。
* 降重在 QThread 里跑，界面不假死，且可以中途取消。
* 数字、参考文献标号在翻译链路里被占位符保护，不会被各语言的数字习惯改写。
* 相同句子第二次翻译命中缓存，不消耗额度。
* 支持导入 txt、导出 txt / docx。
"""

import os
import webbrowser
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame,
                             QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                             QMessageBox, QProgressBar, QPushButton,
                             QScrollArea, QShortcut, QTabWidget, QToolButton,
                             QVBoxLayout, QWidget)

from .. import APP_ID, APP_NAME, APP_NAME_EN, ORG_NAME, __version__
from ..core import export as export_mod
from ..core import metrics, pipeline
from ..core.cache import TranslationCache
from ..core.translator import BaiduTranslator
from ..infra import paths, secret_store
from ..infra.settings import Settings
from . import theme
from .diff_view import DiffView
from .widgets import (AboutDialog, Card, MetricChip, RichTextEdit, StepRow,
                      app_icon, logo_pixmap)
from .worker import ApiTestWorker, TranslateWorker

STATE_COLORS = {
    'ok': theme.COLORS['success'],
    'warn': theme.COLORS['warn'],
    'error': theme.COLORS['danger'],
    'info': theme.COLORS['muted'],
}


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.settings = Settings()
        migrated = self.settings.migrate_legacy()

        self.cache = TranslationCache(enabled=self.settings.cache_enabled())
        self.cache.prune(90)                 # 顺手清理三个月前的旧条目
        self.translator = BaiduTranslator(
            self.settings.get_appid(),
            self.settings.get_appkey(),
            cache=self.cache,
        )
        self.worker = None
        self.test_worker = None

        self._ui_state = QSettings(ORG_NAME, APP_ID)
        self._last_source = ''
        self._last_result = ''

        self._build_ui()
        self._load_settings()
        self._restore_geometry()
        self._refresh_credential_status(
            prefix='已从旧版 config.json 迁移配置。' if migrated else ''
        )
        self._update_estimate()
        self._refresh_cache_hint()

    # ── 构建：外壳 ────────────────────────────────────────
    def _build_ui(self):
        self.setWindowTitle('{} v{}'.format(APP_NAME, __version__))
        self.setWindowIcon(app_icon())

        # 小屏幕上不硬撑 1280×880，否则窗口底边会被屏幕切掉
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(1440, int(available.width() * 0.96))
            height = min(940, int(available.height() * 0.96))
        else:
            width, height = 1440, 940
        self.resize(width, height)
        self.setMinimumSize(min(1180, width), min(760, height))

        root = QWidget()
        root.setObjectName('Root')
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(theme.GAP)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_main(), 1)

        QShortcut(QKeySequence('Ctrl+Return'), self, self.start_translate)
        QShortcut(QKeySequence('Ctrl+E'), self, self.export_result)

    # ── 构建：侧栏 ────────────────────────────────────────
    def _build_sidebar(self):
        container = QWidget()
        container.setFixedWidth(384)

        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 6, 0)
        outer.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        # 注意：不要在这里 setStyleSheet('background: transparent')。
        # 控件级样式表会向下继承到所有子控件，把主按钮的背景一并抹成透明，
        # 结果就是「蓝边框 + 白底 + 白字」这种看不见的按钮。
        content.setObjectName('ScrollBody')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_brand())
        layout.addWidget(self._build_api_card())
        layout.addWidget(self._build_steps_card())
        layout.addWidget(self._build_quota_card())
        layout.addStretch(1)

        scroll.setWidget(content)

        # 底部维护按钮固定在侧栏下沿，不随内容滚动
        outer.addWidget(scroll, 1)
        outer.addLayout(self._build_sidebar_footer())
        return container

    def _build_brand(self):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(2, 2, 2, 6)
        row.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(logo_pixmap(40))
        logo.setFixedSize(40, 40)
        row.addWidget(logo)

        column = QVBoxLayout()
        column.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(7)
        title = QLabel(APP_NAME)
        title.setObjectName('BrandTitle')
        badge = QLabel('v{}'.format(__version__))
        badge.setObjectName('VersionBadge')
        title_row.addWidget(title)
        title_row.addWidget(badge, 0, Qt.AlignVCenter)
        title_row.addStretch()

        subtitle = QLabel('多语言回译 · 长文分段 · 数字保护')
        subtitle.setObjectName('Muted')

        column.addLayout(title_row)
        column.addWidget(subtitle)
        row.addLayout(column, 1)
        return widget

    def _build_api_card(self):
        card = Card('API 凭证')

        self.cred_dot = QLabel('●')
        self.cred_dot.setStyleSheet('color: {}; font-size: 14px;'.format(
            theme.COLORS['muted']))
        card.add_header_widget(self.cred_dot)

        self.appid_edit = QLineEdit()
        self.appid_edit.setPlaceholderText('纯数字，例如 20250101000000000')
        self.appid_edit.setClearButtonEnabled(True)
        card.add(self._field('APPID', self.appid_edit))

        self.appkey_edit = QLineEdit()
        self.appkey_edit.setEchoMode(QLineEdit.Password)
        self.appkey_edit.setPlaceholderText('在百度翻译开放平台获取')
        self.appkey_edit.setClearButtonEnabled(True)

        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(6)
        key_layout.addWidget(self.appkey_edit, 1)

        self.reveal_btn = QToolButton()
        self.reveal_btn.setText('显示')
        self.reveal_btn.setCursor(Qt.PointingHandCursor)
        self.reveal_btn.setFixedWidth(48)
        self.reveal_btn.clicked.connect(self._toggle_key_visibility)
        key_layout.addWidget(self.reveal_btn)
        card.add(self._field('APPKEY', key_row))

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.save_btn = QPushButton('保存配置')
        self.save_btn.setProperty('variant', 'primary')
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.save_config)

        self.test_btn = QPushButton('测试')
        self.test_btn.setCursor(Qt.PointingHandCursor)
        self.test_btn.setToolTip('真实调用一次接口，消耗约 10 字符额度')
        self.test_btn.clicked.connect(self.test_connection)

        register_btn = QPushButton('注册')
        register_btn.setCursor(Qt.PointingHandCursor)
        register_btn.setToolTip('打开百度翻译开放平台')
        register_btn.clicked.connect(
            lambda: webbrowser.open('https://fanyi-api.baidu.com/')
        )

        buttons.addWidget(self.save_btn, 1)
        buttons.addWidget(self.test_btn)
        buttons.addWidget(register_btn)
        card.body.addLayout(buttons)

        self.cred_label = QLabel('')
        self.cred_label.setObjectName('StatusText')
        self.cred_label.setWordWrap(True)
        self.cred_label.setMinimumWidth(1)
        self.cred_label.setTextFormat(Qt.RichText)
        self.cred_label.setMinimumHeight(28)
        card.add(self.cred_label)
        return card

    def _build_steps_card(self):
        card = Card('使用步骤')
        card.body.setSpacing(9)
        card.add(StepRow(
            1, '填写 APPID 与 APPKEY，点「保存配置」。只需配置一次，'
               '下次启动会自动加载。'))
        card.add(StepRow(
            2, '粘贴论文正文。换行即分段，段落与空行都会原样保留，'
               '不需要删掉分段。'))
        card.add(StepRow(
            3, '选好模式后点「开始降重」，中途可取消；'
               '完成后可复制或导出 Word。'))
        return card

    def _build_quota_card(self):
        card = Card('关于额度')
        card.body.setSpacing(7)

        intro = QLabel('每跳都会重译全文，额度 ≈ 字数 × 跳数；命中缓存的部分不消耗额度。')
        intro.setWordWrap(True)
        intro.setMinimumWidth(1)
        intro.setStyleSheet('color: {}; font-size: 13.5px;'.format(
            theme.COLORS['muted']))
        card.add(intro)

        for mode in ('初级', '中级', '高级'):
            hops = pipeline.hop_count(mode)
            row = QWidget()
            row.setToolTip(pipeline.MODE_DESC[mode])
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            name = QLabel(mode)
            name.setStyleSheet('font-size: 14.5px; font-weight: 600;')
            factor = QLabel('约 {} 倍字数'.format(hops))
            factor.setStyleSheet('color: {}; font-size: 12.5px;'.format(
                theme.COLORS['muted']))
            tail = QLabel('{} 跳'.format(hops))
            tail.setStyleSheet('color: {}; font-size: 12.5px;'.format(
                theme.COLORS['primary']))

            row_layout.addWidget(name)
            row_layout.addWidget(factor, 1)
            row_layout.addWidget(tail)
            card.add(row)

        return card

    def _build_sidebar_footer(self):
        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(2)

        for text, slot in (
            ('清空缓存', self.clear_cache),
            ('数据目录', self.open_data_dir),
            ('关于', self.show_about),
        ):
            button = QPushButton(text)
            button.setProperty('variant', 'ghost')
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet('font-size: 13px; padding: 5px 9px;')
            button.clicked.connect(slot)
            row.addWidget(button)

        row.addStretch()
        return row

    @staticmethod
    def _field(label_text, widget):
        """字段 = 小标签 + 控件，避免把标签文字塞进 placeholder。"""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(label_text)
        label.setObjectName('FieldLabel')
        layout.addWidget(label)
        layout.addWidget(widget)
        return holder

    # ── 构建：主区 ────────────────────────────────────────
    def _build_main(self):
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addLayout(self._build_metric_bar())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_edit_tab(), '编辑对照')
        self.diff_view = DiffView()
        self.tabs.addTab(self.diff_view, '差异对比')
        layout.addWidget(self.tabs, 1)

        layout.addLayout(self._build_status_bar())
        return main

    def _build_metric_bar(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(2, 0, 0, 0)

        self.chip_changed = MetricChip('改动率')
        self.chip_keep = MetricChip('保留率')
        self.chip_len = MetricChip('字数')
        for chip in (self.chip_changed, self.chip_keep, self.chip_len):
            row.addWidget(chip)

        note = QLabel('本地估算的文本改动比例，不是查重报告')
        note.setObjectName('Muted')
        row.addSpacing(6)
        row.addWidget(note)
        row.addStretch()

        import_btn = QPushButton('导入 TXT')
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.clicked.connect(self.import_text)

        self.export_btn = QPushButton('导出')
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setToolTip('导出为 Word 或 TXT（Ctrl+E）')
        self.export_btn.clicked.connect(self.export_result)

        row.addWidget(import_btn)
        row.addWidget(self.export_btn)
        return row

    def _build_edit_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_input_card(), 1)
        layout.addWidget(self._build_run_card())
        layout.addWidget(self._build_output_card(), 1)
        return page

    def _build_input_card(self):
        card = Card('原文')

        self.input_counter = QLabel('字符 0 · 段落 0')
        self.input_counter.setObjectName('Muted')
        card.add_header_widget(self.input_counter)

        paste_btn = QPushButton('粘贴')
        paste_btn.setProperty('variant', 'ghost')
        paste_btn.setCursor(Qt.PointingHandCursor)
        paste_btn.clicked.connect(self.paste_text)
        card.add_header_widget(paste_btn)

        clear_btn = QPushButton('清空')
        clear_btn.setProperty('variant', 'ghost')
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self.clear_input)
        card.add_header_widget(clear_btn)

        self.input_text = RichTextEdit(counter=self.input_counter)
        self.input_text.setPlaceholderText(
            '在这里粘贴需要降重的文章…\n换行即分段，段落结构会被保留。')
        self.input_text.setMinimumHeight(172)
        self.input_text.textChanged.connect(self._schedule_estimate)
        card.add(self.input_text, 1)
        return card

    def _build_run_card(self):
        card = Card()
        card.body.setSpacing(9)

        row = QHBoxLayout()
        row.setSpacing(9)

        mode_label = QLabel('降重模式')
        mode_label.setStyleSheet('font-size: 13.5px; color: {};'.format(
            theme.COLORS['muted']))
        row.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(list(pipeline.MODES.keys()))
        self.mode_combo.currentTextChanged.connect(self._update_estimate)
        row.addWidget(self.mode_combo)

        self.start_btn = QPushButton('开始降重')
        self.start_btn.setProperty('variant', 'primary')
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setDefault(True)
        self.start_btn.setToolTip('Ctrl+Enter')
        self.start_btn.clicked.connect(self.start_translate)
        row.addWidget(self.start_btn)

        self.cancel_btn = QPushButton('取消')
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_translate)
        row.addWidget(self.cancel_btn)

        row.addStretch()

        self.estimate_label = QLabel('')
        self.estimate_label.setStyleSheet(
            'color: {}; font-size: 13px;'.format(theme.COLORS['muted']))
        row.addWidget(self.estimate_label)
        card.body.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        card.add(self.progress)

        detail_row = QHBoxLayout()
        detail_row.setSpacing(8)

        self.progress_label = QLabel('')
        self.progress_label.setStyleSheet(
            'color: {}; font-size: 13px;'.format(theme.COLORS['muted']))
        detail_row.addWidget(self.progress_label, 1)

        self.saving_label = QLabel('')
        self.saving_label.setStyleSheet(
            'color: {}; font-size: 13px;'.format(theme.COLORS['success']))
        detail_row.addWidget(self.saving_label)

        card.body.addLayout(detail_row)
        return card

    def _build_output_card(self):
        card = Card('降重结果')

        self.output_counter = QLabel('字符 0 · 段落 0')
        self.output_counter.setObjectName('Muted')
        card.add_header_widget(self.output_counter)

        copy_btn = QPushButton('复制')
        copy_btn.setProperty('variant', 'ghost')
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self.copy_text)
        card.add_header_widget(copy_btn)

        export_btn = QPushButton('导出')
        export_btn.setProperty('variant', 'ghost')
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self.export_result)
        card.add_header_widget(export_btn)

        self.output_text = RichTextEdit(counter=self.output_counter)
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText('降重结果会显示在这里…')
        self.output_text.setMinimumHeight(172)
        card.add(self.output_text, 1)
        return card

    def _build_status_bar(self):
        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(10)

        self.status_label = QLabel('就绪')
        self.status_label.setObjectName('StatusText')
        self.status_label.setTextFormat(Qt.RichText)
        self.status_label.setMinimumWidth(1)
        row.addWidget(self.status_label, 1)

        self.cache_label = QLabel('')
        self.cache_label.setObjectName('Muted')
        row.addWidget(self.cache_label)
        return row

    # ── 配置 ──────────────────────────────────────────────
    def _load_settings(self):
        self.appid_edit.setText(self.settings.get_appid())
        self.appkey_edit.setText(self.settings.get_appkey())

        mode = self.settings.get_mode()
        index = self.mode_combo.findText(mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)

    def _toggle_key_visibility(self):
        if self.appkey_edit.echoMode() == QLineEdit.Password:
            self.appkey_edit.setEchoMode(QLineEdit.Normal)
            self.reveal_btn.setText('隐藏')
        else:
            self.appkey_edit.setEchoMode(QLineEdit.Password)
            self.reveal_btn.setText('显示')

    def _refresh_credential_status(self, prefix=''):
        """凭证状态：就绪与否 + 密钥怎么存的，合成一句。

        v1 的顺序会让空配置的用户看到一句绿色的「密钥已加密」，
        误以为可以直接用。
        """
        backend = secret_store.backend_name()

        if not self.settings.has_credentials():
            level = 'warn'
            dot = theme.COLORS['warn']
            text = '尚未配置凭证，点「注册」获取 APPID / APPKEY。'
        elif backend == 'obfuscated':
            level = 'warn'
            dot = theme.COLORS['warn']
            text = '凭证已保存，但密钥未加密存储，建议安装 keyring。'
        else:
            level = 'ok'
            dot = theme.COLORS['success']
            backend_text = ('系统凭据管理器' if backend == 'keyring'
                            else 'Windows DPAPI')
            text = '凭证已就绪，密钥存储于{}（已加密）。'.format(backend_text)

        if prefix:
            text = prefix + ' ' + text

        self.cred_dot.setStyleSheet('color: {}; font-size: 14px;'.format(dot))
        self.cred_label.setText(
            '<span style="color:{};">{}</span>'.format(
                STATE_COLORS[level], text)
        )

    def _set_status(self, text, level='info'):
        color = STATE_COLORS.get(level, STATE_COLORS['info'])
        self.status_label.setText(
            '<span style="color:{};">{}</span>'.format(color, text)
        )

    def save_config(self):
        if not self._sync_credentials(show_error=True):
            return
        self._refresh_credential_status()
        self._set_status('配置已保存，下次启动自动加载。', 'ok')

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

        self.test_btn.setEnabled(False)
        self._set_status('正在测试连接…', 'info')

        self.test_worker = ApiTestWorker(self.translator, self)
        self.test_worker.succeeded.connect(self._on_test_ok)
        self.test_worker.failed.connect(self._on_test_failed)
        self.test_worker.finished.connect(lambda: self.test_btn.setEnabled(True))
        self.test_worker.start()

    def _on_test_ok(self, result):
        self._set_status('连接正常：测试连接 → {}'.format(result), 'ok')

    def _on_test_failed(self, message):
        self._refresh_credential_status()
        self._set_status('连接失败：{}'.format(message), 'error')
        QMessageBox.warning(self, '验证失败', message)

    # ── 额度预估 ──────────────────────────────────────────
    def _schedule_estimate(self):
        if not hasattr(self, '_estimate_timer'):
            self._estimate_timer = QTimer(self)
            self._estimate_timer.setSingleShot(True)
            self._estimate_timer.setInterval(300)
            self._estimate_timer.timeout.connect(self._update_estimate)
        self._estimate_timer.start()

    def _update_estimate(self):
        text = self.input_text.toPlainText() if hasattr(self, 'input_text') else ''
        if not text.strip():
            self.estimate_label.setText('')
            return

        mode = self.mode_combo.currentText() if hasattr(self, 'mode_combo') else '初级'
        calls = pipeline.estimate_requests(text, mode)
        chars = pipeline.estimate_chars(text, mode)
        hops = pipeline.hop_count(mode)
        self.estimate_label.setText(
            '预计 {} 次请求 · 约 {:,} 字符额度（{} 跳）'.format(calls, chars, hops)
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

        hops = pipeline.hop_count(mode)
        estimate = pipeline.estimate_chars(text, mode)
        if estimate > 40000:
            answer = QMessageBox.question(
                self, '额度提醒',
                '本次预计消耗约 {:,} 字符额度（{} 跳 × {} 字）。\n确定继续吗？'
                .format(estimate, hops, len(text)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        self._last_source = text
        self._last_result = ''
        self.output_text.set_text('')
        self.diff_view.clear()
        self.progress.setValue(0)
        self.progress_label.setText('准备中…')
        self.saving_label.setText('')
        self.chip_changed.set_value('—')
        self.chip_keep.set_value('—')
        self.chip_len.set_value('—')
        self._set_status('正在降重，请稍候…', 'info')
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
            self._set_status('正在取消…', 'warn')

    def _set_busy(self, busy):
        self.start_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.mode_combo.setEnabled(not busy)
        self.save_btn.setEnabled(not busy)
        self.test_btn.setEnabled(not busy)
        self.appid_edit.setEnabled(not busy)
        self.appkey_edit.setEnabled(not busy)
        self.input_text.setReadOnly(busy)
        self.tabs.tabBar().setEnabled(not busy)

    def _on_progress(self, percent, message):
        self.progress.setValue(percent)
        self.progress_label.setText(message)

    def _on_success(self, result, report, stats):
        self._set_busy(False)
        self._last_result = result
        self.output_text.set_text(result)
        self.progress.setValue(100)
        self.progress_label.setText('已完成')

        self.chip_changed.set_value('{:.1f}%'.format(report['changed_ratio'] * 100))
        self.chip_keep.set_value('{:.1f}%'.format(report['retention'] * 100))
        self.chip_len.set_value('{} → {}'.format(
            report['len_before'], report['len_after']))

        self.diff_view.show_diff(self._last_source, result)
        self._show_saving(stats)
        self._refresh_cache_hint()
        self._set_status('降重完成。' + metrics.format_report(report), 'ok')

    def _show_saving(self, stats):
        parts = []
        if stats.get('cache_hits'):
            parts.append('命中缓存 {} 次 · 省下 {:,} 字符'.format(
                stats['cache_hits'], stats['chars_saved']))
        if stats.get('protected_tokens'):
            parts.append('保护 {} 处数字/标号'.format(stats['protected_tokens']))
        self.saving_label.setText(' · '.join(parts))

    def _on_failed(self, message, detail):
        self._set_busy(False)
        self.progress.setValue(0)
        self.progress_label.setText('')
        self.chip_changed.set_value('—')
        self.chip_keep.set_value('—')
        self.chip_len.set_value('—')
        self._set_status('失败：{}'.format(message), 'error')
        if detail:
            print(detail)
        QMessageBox.warning(self, '降重失败', message)

    def _on_cancelled(self):
        self._set_busy(False)
        self.progress.setValue(0)
        self.progress_label.setText('已取消')
        self._set_status('已取消。已翻译的片段已写入缓存，重跑不会重复计费。', 'warn')

    # ── 剪贴板 / 文件 ─────────────────────────────────────
    def paste_text(self):
        text = QApplication.clipboard().text()
        if text:
            self.input_text.set_text(text)
            self._update_estimate()
            self._set_status('已从剪贴板粘贴 {} 字。'.format(len(text)), 'ok')

    def copy_text(self):
        text = self.output_text.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._set_status('已复制到剪贴板。', 'ok')

    def clear_input(self):
        self.input_text.set_text('')
        self.output_text.set_text('')
        self.diff_view.clear()
        self.progress.setValue(0)
        self.progress_label.setText('')
        self.saving_label.setText('')
        self.estimate_label.setText('')
        for chip in (self.chip_changed, self.chip_keep, self.chip_len):
            chip.set_value('—')

    def import_text(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '导入文本', '', '文本文件 (*.txt *.md);;所有文件 (*.*)')
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
        except OSError as exc:
            QMessageBox.warning(self, '读取失败', str(exc))
            return

        for encoding in ('utf-8-sig', 'utf-8', 'gbk'):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            QMessageBox.warning(self, '读取失败', '无法识别文件编码。')
            return

        self.input_text.set_text(text)
        self._update_estimate()
        self._set_status('已导入 {}（{} 字）。'.format(Path(path).name, len(text)), 'ok')

    def export_result(self):
        text = self.output_text.toPlainText()
        if not text.strip():
            QMessageBox.information(self, '暂无结果', '先完成一次降重，再导出。')
            return

        default_name = '降重结果_{}.docx'.format(datetime.now().strftime('%m%d_%H%M'))
        path, selected = QFileDialog.getSaveFileName(
            self, '导出结果', default_name,
            'Word 文档 (*.docx);;纯文本 (*.txt)')

        if not path:
            return
        if not Path(path).suffix:
            path += '.txt' if 'txt' in selected else '.docx'

        try:
            export_mod.save(text, path, source=self._last_source,
                            title='降重结果')
        except ImportError:
            QMessageBox.warning(
                self, '无法导出 Word',
                '未安装 python-docx，将导出为 TXT。\n'
                '安装后可导出 Word：pip install python-docx')
            path = str(Path(path).with_suffix('.txt'))
            export_mod.to_txt(text, path)
        except OSError as exc:
            QMessageBox.warning(self, '导出失败', str(exc))
            return

        self._set_status('已导出：{}'.format(Path(path).name), 'ok')

    # ── 维护 ──────────────────────────────────────────────
    def _refresh_cache_hint(self):
        count, size = self.cache.stats()
        if not self.settings.cache_enabled():
            self.cache_label.setText('缓存已关闭')
            return
        if size >= 1024 * 1024:
            human = '{:.1f} MB'.format(size / 1024 / 1024)
        else:
            human = '{:.0f} KB'.format(size / 1024)
        self.cache_label.setText('缓存 {} 条 · {}'.format(count, human))

    def clear_cache(self):
        count, _ = self.cache.stats()
        if not count:
            self._set_status('缓存已经是空的。', 'info')
            return
        answer = QMessageBox.question(
            self, '清空缓存',
            '将删除 {} 条已翻译的句子。\n清空后同样的内容会重新计费。继续吗？'
            .format(count),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        removed = self.cache.clear()
        self._refresh_cache_hint()
        self._set_status('已清空 {} 条缓存。'.format(removed), 'ok')

    def open_data_dir(self):
        target = paths.data_dir()
        try:
            os.startfile(str(target))      # noqa: S606  Windows 专用
        except AttributeError:
            webbrowser.open(target.as_uri())
        except OSError as exc:
            QMessageBox.warning(self, '无法打开', str(exc))

    def show_about(self):
        AboutDialog(self).exec_()

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

        self.translator.close()
        super().closeEvent(event)


def _install_excepthook():
    """未捕获异常写入日志并弹窗，避免打包后的 exe 静默退出。"""
    import sys
    import traceback

    log_path = paths.log_path()

    def hook(exc_type, exc_value, exc_tb):
        detail = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(log_path, 'a', encoding='utf-8') as handle:
                handle.write('\n[{}]\n{}'.format(
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'), detail))
        except OSError:
            pass
        QMessageBox.critical(
            None, '程序出错',
            '发生了什么：{}\n\n详细信息已写入：\n{}'.format(exc_value, log_path),
        )

    sys.excepthook = hook


def main():
    import sys

    from PyQt5.QtCore import Qt as _Qt
    from PyQt5.QtWidgets import QApplication as _QApplication

    from .widgets import default_font

    _QApplication.setAttribute(_Qt.AA_EnableHighDpiScaling, True)
    _QApplication.setAttribute(_Qt.AA_UseHighDpiPixmaps, True)

    # 让任务栏使用自带图标，而不是 Python 的图标
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                'ZeroOne.ArticleReducer.2')
        except Exception:
            pass

    app = _QApplication(sys.argv)
    app.setApplicationName(APP_NAME_EN)
    app.setOrganizationName(ORG_NAME)
    # 注意：不要设 setApplicationDisplayName，Qt 会把它追加到每个窗口标题后面，
    # 标题会变成「文章降重助手 v2.0.0 · 文章降重助手」。
    app.setWindowIcon(app_icon())
    app.setFont(default_font())
    theme.apply(app)

    _install_excepthook()

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
