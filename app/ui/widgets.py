# -*- coding: utf-8 -*-
"""可复用控件。

拆出来的目的是让主窗口只负责「摆位置 + 接信号」，不再出现 v1 里
「一个方法里既建控件又写样式又管业务」的场面。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon, QPixmap, QTextBlockFormat, QTextCursor
from PyQt5.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QTextEdit, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..infra import paths
from . import theme


# ── 图标 ──────────────────────────────────────────────────
def app_icon():
    """窗口 / 任务栏图标。优先用多尺寸 ico。"""
    ico = paths.resource_path('icon.ico')
    if ico.exists():
        return QIcon(str(ico))
    png = paths.resource_path('icon_256.png')
    if png.exists():
        return QIcon(str(png))
    return QIcon()


def logo_pixmap(size=36):
    """侧栏 LOGO。用 128px 源图缩放，高 DPI 下也不糊。"""
    for name in ('icon_128.png', 'icon_64.png', 'icon_256.png'):
        path = paths.resource_path(name)
        if path.exists():
            pixmap = QPixmap(str(path))
            return pixmap.scaled(size, size, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
    return QPixmap()


# ── 容器 ──────────────────────────────────────────────────
class Card(QFrame):
    """白底卡片。标题行右侧可以继续塞控件。"""

    def __init__(self, title=None, hint=None, parent=None):
        super().__init__(parent)
        self.setObjectName('Card')

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(11)

        self.header_row = None
        if title:
            row = QHBoxLayout()
            row.setSpacing(8)
            self.title_label = QLabel(title)
            self.title_label.setObjectName('CardTitle')
            row.addWidget(self.title_label)
            if hint:
                hint_label = QLabel(hint)
                hint_label.setObjectName('Muted')
                row.addWidget(hint_label)
            row.addStretch()
            outer.addLayout(row)
            self.header_row = row

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)

    def add_header_widget(self, widget):
        if self.header_row is not None:
            self.header_row.addWidget(widget)
        return widget

    def add(self, widget, stretch=0):
        self.body.addWidget(widget, stretch)
        return widget


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('Divider')
        self.setFixedHeight(1)


class StepRow(QWidget):
    """使用步骤：圆形序号 + 说明文字。"""

    def __init__(self, index, text, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        badge = QLabel(str(index))
        badge.setObjectName('StepBadge')
        badge.setFixedSize(24, 24)
        badge.setAlignment(Qt.AlignCenter)

        label = QLabel(text)
        label.setObjectName('StepText')
        label.setWordWrap(True)
        # 中文没有空格，QLabel 会把整段当作一个「单词」，
        # 于是最小宽度等于整段文字宽度，侧栏直接被撑破。
        label.setMinimumWidth(1)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(badge, 0, Qt.AlignTop)
        layout.addWidget(label, 1, Qt.AlignTop)


class MetricChip(QFrame):
    """顶部指标小块。"""

    def __init__(self, name, value='—', parent=None):
        super().__init__(parent)
        self.setObjectName('Chip')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 7, 13, 7)
        layout.setSpacing(0)

        self.name_label = QLabel(name)
        self.name_label.setObjectName('ChipName')
        self.value_label = QLabel(value)
        self.value_label.setObjectName('ChipValue')

        layout.addWidget(self.name_label)
        layout.addWidget(self.value_label)

    def set_value(self, value, color=None):
        self.value_label.setText(value)
        self.value_label.setStyleSheet(
            'color: {};'.format(color) if color else ''
        )


# ── 编辑框 ────────────────────────────────────────────────
class RichTextEdit(QTextEdit):
    """论文正文编辑框：首行缩进两字、纯文本粘贴、字数统计。"""

    def __init__(self, counter=None, parent=None):
        super().__init__(parent)
        self._counter = counter
        self.setStyleSheet(
            # 先写中文名：部分机器只注册了「宋体」而没有 SimSun 这个别名，
            # 写成 SimSun 会匹配失败并回退到字距难看的默认字体。
            'QTextEdit {{ font-family: {}; font-size: {}px; }}'.format(
                theme.FONT_BODY, theme.EDITOR_PX)
        )
        self.textChanged.connect(self.update_counter)
        self._apply_indent()

    def _block_format(self):
        fmt = QTextBlockFormat()
        fmt.setAlignment(Qt.AlignJustify)
        # 缩进按「两个汉字宽度」算，换字号也不会错位（v1 写死 24 像素）
        fmt.setTextIndent(self.fontMetrics().horizontalAdvance('中') * 2)
        fmt.setLineHeight(180, QTextBlockFormat.ProportionalHeight)
        return fmt

    def _apply_indent(self):
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setBlockFormat(self._block_format())

    def set_text(self, text):
        """设纯文本并恢复缩进。"""
        self.setPlainText(text or '')
        self._apply_indent()
        self.update_counter()

    def update_counter(self):
        if self._counter is None:
            return
        text = self.toPlainText()
        paragraphs = sum(1 for line in text.split('\n') if line.strip())
        # 中文没有空格，按空白切分的「词数」恒为 1，没有参考价值，改报段落数
        self._counter.setText('字符 {} · 段落 {}'.format(len(text), paragraphs))

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


# ── 关于 ──────────────────────────────────────────────────
class AboutDialog(QDialog):
    """关于窗口。放版本号与两条必须讲清楚的话。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('关于 {}'.format(APP_NAME))
        self.setWindowIcon(app_icon())
        self.setFixedWidth(500)
        self.setStyleSheet(
            'QDialog {{ background: {}; }}'.format(theme.COLORS['surface']))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 20)
        layout.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(54))
        head.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        name = QLabel(APP_NAME)
        name.setStyleSheet('font-size: 21px; font-weight: 700;')
        version = QLabel('版本 {} · 基于百度翻译开放接口'.format(__version__))
        version.setObjectName('Muted')
        titles.addWidget(name)
        titles.addWidget(version)
        head.addLayout(titles)
        head.addStretch()
        layout.addLayout(head)

        layout.addWidget(Divider())

        body = QLabel(
            '<p style="line-height:1.9; color:#44516B; font-size:14px;">'
            '通过「中 → 英 → 德 → … → 中」的多语言回译打散原文句式，'
            '用于论文写作阶段的表达润色。</p>'
            '<p style="line-height:1.9; color:#44516B; font-size:14px;">'
            '界面上显示的「改动率 / 保留率」是本地按编辑距离算出的'
            '<b>文本改动比例</b>，<b>不是</b>知网、维普的查重结果。'
            '真实重复率只能到检测平台跑。</p>'
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        footer = QLabel('数据目录：{}'.format(paths.data_dir()))
        footer.setObjectName('Muted')
        footer.setWordWrap(True)
        footer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(footer)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close = QPushButton('关闭')
        close.setProperty('variant', 'primary')
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)


def default_font():
    """全局界面字体。"""
    font = QFont()
    font.setFamilies(['微软雅黑', 'Microsoft YaHei', 'PingFang SC', 'Segoe UI'])
    font.setPointSize(11)
    font.setHintingPreference(QFont.PreferFullHinting)
    return font


__all__ = [
    'AboutDialog', 'Card', 'Divider', 'MetricChip', 'RichTextEdit',
    'StepRow', 'app_icon', 'default_font', 'logo_pixmap',
]
