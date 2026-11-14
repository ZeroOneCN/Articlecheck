# -*- coding: utf-8 -*-
"""界面设计系统。

v1 的界面有三个直观问题，都是「没有统一约束」造成的：

1. ``QGroupBox`` 自带灰色渐变标题栏，里面又套了 ``#fafafa`` 的说明框，
   于是右侧出现「灰 — 白 — 灰」多层底色，边看边怀疑自己显示器坏了。
2. 说明文字用了 12px，中文在这个字号下笔画发虚。
3. 颜色散落在各个文件的 ``setStyleSheet`` 里，改一处漏三处。

这里把颜色、字号、圆角、间距集中成设计令牌，再用一份全局 QSS 施加。
整个界面只有两种底色：页面浅底 + 卡片白底。
"""

import re

#: 设计令牌。改这里就能整体换肤，不用翻各个窗口文件。
COLORS = {
    # 底色：只有页面底与卡片底两种，不再有第三层灰
    'page': '#F3F5FA',
    'surface': '#FFFFFF',
    'surface_sunken': '#F8FAFD',

    'border': '#E3E8F1',
    'border_strong': '#D2DAE7',

    'text': '#16202E',
    'text_soft': '#44516450',
    'muted': '#77839A',

    'primary': '#2F5BEA',
    'primary_hover': '#2549C6',
    'primary_pressed': '#1D3AA6',
    'primary_soft': '#EBF0FF',

    'success': '#0E7A57',
    'success_soft': '#E6F5EF',
    'warn': '#A65A08',
    'warn_soft': '#FCF2E2',
    'danger': '#BE3B2E',
    'danger_soft': '#FCECEA',
}

#: 中文界面字体。带英文回退，避免在没装雅黑的机器上退化成难看的默认字体。
FONT_UI = '"微软雅黑", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif'
#: 正文编辑区字体，按论文习惯用宋体
FONT_BODY = '"宋体", "SimSun", "Songti SC", serif'

#: 字号刻度（像素）。整套界面的字号只从这里取，
#: 想整体放大就改这里，不用翻各个窗口文件。
TYPE = {
    'fs_micro': 12,    # 徽章、图例
    'fs_small': 13,    # 次要说明、状态
    'fs_body': 14,     # 输入框、按钮
    'fs_strong': 15,   # 卡片标题、使用步骤
    'fs_num': 16,      # 指标数值
    'fs_brand': 19,    # 品牌标题
}

#: 正文编辑区字号，论文正文要能长时间盯着看，比界面控件大一档
EDITOR_PX = 17

#: 圆角与间距，写在一个地方便于统一
RADIUS = 12
GAP = 14

_QSS = """
/* ── 基础 ───────────────────────────────────────────── */
QWidget {
    color: $text;
}
QWidget#Root {
    background: $page;
}
QLabel {
    background: transparent;
}
QLabel#CardTitle {
    font-size: $fs_strong;
    font-weight: 600;
    color: $text;
}
QLabel#BrandTitle {
    font-size: $fs_brand;
    font-weight: 700;
    color: $text;
}
QLabel#Muted {
    color: $muted;
    font-size: $fs_small;
}
QLabel#StepText {
    font-size: $fs_strong;
    color: #33415A;
}
QLabel#StepBadge {
    background: $primary_soft;
    color: $primary;
    border-radius: 12px;
    font-size: $fs_micro;
    font-weight: 700;
}
QLabel#VersionBadge {
    background: $primary_soft;
    color: $primary;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: $fs_micro;
    font-weight: 600;
}
QLabel#FieldLabel {
    font-size: $fs_small;
    color: $muted;
}
QLabel#StatusText {
    font-size: $fs_small;
}

/* ── 卡片 ───────────────────────────────────────────── */
QFrame#Card {
    background: $surface;
    border: 1px solid $border;
    border-radius: 12px;
}
QFrame#Divider {
    background: $border;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QFrame#Chip {
    background: $surface_sunken;
    border: 1px solid $border;
    border-radius: 9px;
}
QLabel#ChipName {
    color: $muted;
    font-size: $fs_micro;
}
QLabel#ChipValue {
    color: $text;
    font-size: $fs_num;
    font-weight: 700;
}

/* ── 输入控件 ───────────────────────────────────────── */
QLineEdit {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: 8px;
    padding: 8px 11px;
    font-size: $fs_body;
    selection-background-color: #CBD9FF;
    selection-color: $text;
}
QLineEdit:focus {
    border: 1px solid $primary;
}
QLineEdit:disabled {
    background: $surface_sunken;
    color: $muted;
}
QComboBox {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: 8px;
    padding: 7px 10px;
    font-size: $fs_body;
    min-width: 108px;
}
QComboBox:focus {
    border: 1px solid $primary;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
    outline: none;
    selection-background-color: $primary_soft;
    selection-color: $primary;
}

QTextEdit, QPlainTextEdit {
    background: $surface;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 8px;
    selection-background-color: #CBD9FF;
    selection-color: $text;
}
QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #B9C8EA;
}

/* ── 按钮 ───────────────────────────────────────────── */
QPushButton {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: $fs_body;
    color: #2C3748;
}
QPushButton:hover {
    background: #F5F8FF;
    border-color: #BFCCE6;
}
QPushButton:pressed {
    background: #ECF1FB;
}
QPushButton:disabled {
    background: $surface_sunken;
    color: #A7B1C2;
    border-color: $border;
}
QPushButton[variant="primary"] {
    background: $primary;
    border: 1px solid $primary;
    color: #FFFFFF;
    font-weight: 600;
    padding: 10px 22px;
}
QPushButton[variant="primary"]:hover {
    background: $primary_hover;
    border-color: $primary_hover;
}
QPushButton[variant="primary"]:pressed {
    background: $primary_pressed;
}
QPushButton[variant="primary"]:disabled {
    background: #B7C6F1;
    border-color: #B7C6F1;
    color: #F2F5FF;
}
QPushButton[variant="ghost"] {
    background: transparent;
    border: none;
    color: #5A6779;
}
QPushButton[variant="ghost"]:hover {
    background: #E9EEF9;
    color: $text;
}
QPushButton[variant="danger"] {
    color: $danger;
    border-color: #EFD6D2;
    background: $surface;
}
QPushButton[variant="danger"]:hover {
    background: $danger_soft;
    border-color: #E4BFB9;
}

QToolButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 2px 6px;
    color: $muted;
    font-size: $fs_small;
}
QToolButton:hover {
    background: #E9EEF9;
    color: $text;
}

/* ── 进度条 ─────────────────────────────────────────── */
QProgressBar {
    background: #E7ECF6;
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #5C86F7, stop:1 $primary);
    border-radius: 4px;
}

/* ── 选项卡 ─────────────────────────────────────────── */
QTabWidget::pane {
    border: none;
    background: transparent;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #5A6779;
    padding: 9px 20px;
    margin-right: 6px;
    border-radius: 9px;
    font-size: $fs_body;
}
QTabBar::tab:hover {
    background: #E9EEF9;
    color: $text;
}
QTabBar::tab:selected {
    background: $surface;
    color: $primary;
    font-weight: 600;
    border: 1px solid $border;
}

/* ── 滚动条 ─────────────────────────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #CFD8E6;
    border-radius: 5px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover {
    background: #B4C0D4;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #CFD8E6;
    border-radius: 5px;
    min-width: 32px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ── 滚动区 ─────────────────────────────────────────── */
QScrollArea {
    background: transparent;
    border: none;
}
QWidget#ScrollBody {
    background: transparent;
}

/* ── 弹窗与提示 ─────────────────────────────────────── */
QToolTip {
    background: #1B2434;
    color: #FFFFFF;
    border: none;
    padding: 6px 9px;
    border-radius: 6px;
    font-size: $fs_small;
}
QDialog {
    background: $page;
}
QMessageBox {
    background: $page;
}
QMenu {
    background: $surface;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 24px 8px 14px;
    border-radius: 6px;
    font-size: $fs_body;
}
QMenu::item:selected {
    background: $primary_soft;
    color: $primary;
}
QMenu::separator {
    height: 1px;
    background: $border;
    margin: 5px 8px;
}
"""

_TOKEN = re.compile(r'\$([a-z_]+)')


def stylesheet():
    """把颜色与字号令牌填进 QSS 模板。"""
    table = dict(COLORS)
    table.update({name: '{}px'.format(size) for name, size in TYPE.items()})

    def _sub(match):
        return table.get(match.group(1), match.group(0))

    return _TOKEN.sub(_sub, _QSS)


def apply(app):
    """给 QApplication 施加全局样式。"""
    app.setStyle('Fusion')
    app.setStyleSheet(stylesheet())
