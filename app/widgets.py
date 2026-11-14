# -*- coding: utf-8 -*-
"""可复用控件。

拆出来的目的是让主窗口只负责「摆位置 + 接信号」，不再出现 v1 里
「一个方法里既建控件又写样式又管业务」的场面。

其中 ``SegmentedControl`` 与 ``ModeSelect`` 是自绘控件：

* ``QTabWidget`` 在 Fusion 样式下会在页签行上画一条 1px 基线（那条
  悬空的横线），样式表关不掉，所以换成自绘分段控件 + ``QStackedWidget``。
* ``QComboBox`` 的下拉弹层是独立顶层窗口，圆角、行高、右侧箭头都很难
  调干净，而且它只能放一行纯文本。这里自绘按钮 + 自绘弹层，
  顺便把「跳数」和「语言链路」摆进选项里。
"""

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QIcon, QPainter, QPen,
                        QPixmap, QTextBlockFormat, QTextCursor)
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QDialog, QFrame,
                             QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QTextEdit, QVBoxLayout, QWidget)

from . import APP_NAME, __version__
from . import paths
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


# ── 分段控件（替代 QTabWidget）────────────────────────────
class SegmentedControl(QFrame):
    """分段切换器：浅色轨道 + 白色胶囊。

    换掉 ``QTabWidget`` 的原因是 Fusion 样式会在页签行上补一条 1px 基线，
    页签做成胶囊以后那条线就变成一段悬空的横线，样式表关不掉它。
    """

    changed = pyqtSignal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName('Segmented')
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for index, label in enumerate(labels):
            button = QPushButton(label)
            button.setObjectName('Segment')
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(index == 0)
            self._group.addButton(button, index)
            layout.addWidget(button)

        self._group.buttonClicked[int].connect(self.changed)

    def current_index(self):
        return max(self._group.checkedId(), 0)

    def set_current(self, index):
        button = self._group.button(index)
        if button is not None and not button.isChecked():
            button.setChecked(True)
            self.changed.emit(index)


# ── 降重模式选择器 ────────────────────────────────────────
class _ModePopup(QFrame):
    """模式弹层。每个选项两行：模式名 + 跳数，下面是语言链路。"""

    picked = pyqtSignal(int)
    closed = pyqtSignal()

    PAD = 6
    HEADER = 34
    ROW_H = 54
    #: 高级模式的链路最长（300px / 12px 字），宽度按它定，避免出现省略号
    WIDTH = 344

    def __init__(self, options, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._options = list(options)
        self._selected = 0
        self._hover = -1
        self.setFixedSize(self.WIDTH,
                          self.HEADER + self.ROW_H * len(self._options)
                          + self.PAD * 2)

    # ── 布局 ──────────────────────────────────────────────
    def _row_at(self, point):
        if point.y() < self.HEADER + self.PAD:
            return -1
        index = int((point.y() - self.HEADER - self.PAD) // self.ROW_H)
        return index if 0 <= index < len(self._options) else -1

    def set_selected(self, index):
        self._selected = index
        self._hover = index
        self.update()

    def popup_at(self, below, above):
        screen = QApplication.screenAt(below) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        top = below.y()
        if top + self.height() > available.bottom() - 8:
            top = max(above.y() - self.height(), available.top() + 8)
        self.move(below.x(), top)
        self.show()
        self.setFocus()

    # ── 绘制 ──────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(theme.COLORS['border_strong']), 1))
        painter.setBrush(QColor(theme.COLORS['surface']))
        painter.drawRoundedRect(card, 12, 12)

        hint_font = QFont(self.font())
        hint_font.setPixelSize(12)
        painter.setFont(hint_font)
        painter.setPen(QColor(theme.COLORS['muted']))
        painter.drawText(
            QRectF(14, 0, self.WIDTH - 28, self.HEADER),
            Qt.AlignLeft | Qt.AlignVCenter,
            '跳数越多，句式改得越彻底，术语也越容易漂移',
        )

        name_font = QFont(self.font())
        name_font.setPixelSize(15)
        name_font.setWeight(QFont.DemiBold)

        chain_font = QFont(self.font())
        chain_font.setPixelSize(12)

        chip_font = QFont(self.font())
        chip_font.setPixelSize(11)
        chip_font.setWeight(QFont.DemiBold)
        chip_metrics = QFontMetrics(chip_font)

        for index, (name, hops, chain) in enumerate(self._options):
            row = QRectF(self.PAD, self.HEADER + self.PAD + index * self.ROW_H,
                         self.WIDTH - self.PAD * 2, self.ROW_H - 4)
            selected = index == self._selected

            if selected:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(theme.COLORS['primary_soft']))
                painter.drawRoundedRect(row, 9, 9)
            elif index == self._hover:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(theme.COLORS['surface_sunken']))
                painter.drawRoundedRect(row, 9, 9)

            # 模式名
            painter.setFont(name_font)
            painter.setPen(QColor(theme.COLORS['primary'] if selected
                                  else theme.COLORS['text']))
            painter.drawText(QRectF(row.x() + 13, row.y() + 6, 150, 24),
                             Qt.AlignLeft | Qt.AlignVCenter, name)

            # 跳数徽章，靠右
            label = '{} 跳'.format(hops)
            chip = QRectF(row.right() - 13 - chip_metrics.horizontalAdvance(label) - 14,
                          row.y() + 9, chip_metrics.horizontalAdvance(label) + 14, 19)
            if selected:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(theme.COLORS['primary']))
                painter.drawRoundedRect(chip, 6, 6)
                chip_color = '#FFFFFF'
            else:
                painter.setPen(QPen(QColor(theme.COLORS['border_strong']), 1))
                painter.setBrush(QColor(theme.COLORS['surface']))
                painter.drawRoundedRect(chip, 6, 6)
                chip_color = theme.COLORS['primary']

            painter.setFont(chip_font)
            painter.setPen(QColor(chip_color))
            painter.drawText(chip, Qt.AlignCenter, label)

            # 语言链路，超长自动省略
            painter.setFont(chain_font)
            painter.setPen(QColor(theme.COLORS['muted']))
            available = int(row.width() - 26)
            text = QFontMetrics(chain_font).elidedText(
                chain, Qt.ElideRight, available)
            painter.drawText(QRectF(row.x() + 13, row.y() + 29, available, 18),
                             Qt.AlignLeft | Qt.AlignVCenter, text)

    # ── 交互 ──────────────────────────────────────────────
    def _move(self, step):
        self._selected = (self._selected + step) % len(self._options)
        self._hover = self._selected
        self.update()

    def mouseMoveEvent(self, event):
        index = self._row_at(event.pos())
        if index != self._hover:
            self._hover = index
            self.update()

    def mouseReleaseEvent(self, event):
        index = self._row_at(event.pos())
        if index >= 0:
            self.picked.emit(index)
        self.close()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Down, Qt.Key_Tab):
            self._move(1)
        elif key == Qt.Key_Up:
            self._move(-1)
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.picked.emit(self._selected)
            self.close()
        elif key == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.closed.emit()


class _TriggerButton(QPushButton):
    """下拉触发按钮：右侧箭头自己画，不依赖图片资源。"""

    open_requested = pyqtSignal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._open = False
        self.setCursor(Qt.PointingHandCursor)

    def set_open(self, opened):
        if self._open != opened:
            self._open = opened
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)               # 背景、边框、文字交给 QSS

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(theme.COLORS['primary'] if self._open
                          else theme.COLORS['muted']), 1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        cx = self.width() - 16.0
        cy = self.height() / 2.0
        if self._open:
            painter.drawPolyline(QPointF(cx - 4.5, cy + 2),
                                 QPointF(cx, cy - 2.5),
                                 QPointF(cx + 4.5, cy + 2))
        else:
            painter.drawPolyline(QPointF(cx - 4.5, cy - 2),
                                 QPointF(cx, cy + 2.5),
                                 QPointF(cx + 4.5, cy - 2))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Down, Qt.Key_F4):
            self.open_requested.emit()
            return
        super().keyPressEvent(event)


class ModeSelect(QWidget):
    """降重模式下拉。对外接口只留三个方法，和原来的 QComboBox 用法对齐。"""

    currentTextChanged = pyqtSignal(str)

    def __init__(self, options, parent=None):
        """options: ``[(模式名, 跳数, 语言链路), ...]``"""
        super().__init__(parent)
        self._options = [tuple(item) for item in options]
        self._index = 0
        self._popup = None

        self._button = _TriggerButton(self._options[0][0])
        self._button.setObjectName('ModeButton')
        self._button.setMinimumWidth(162)
        self._button.setToolTip('点击选择降重模式')
        self._button.clicked.connect(self._toggle)
        self._button.open_requested.connect(self._open)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._button)

    # ── 对外 ──────────────────────────────────────────────
    def current_text(self):
        return self._options[self._index][0]

    def set_current_text(self, name):
        for index, (label, _, _) in enumerate(self._options):
            if label == name:
                self._select(index, emit=False)
                return

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        if not enabled:
            self._close()

    # ── 内部 ──────────────────────────────────────────────
    def _select(self, index, emit=True):
        if not 0 <= index < len(self._options):
            return
        changed = index != self._index
        self._index = index
        self._button.setText(self._options[index][0])
        if emit and changed:
            self.currentTextChanged.emit(self._options[index][0])

    def _toggle(self):
        if self._popup is not None and self._popup.isVisible():
            self._close()
        else:
            self._open()

    def _open(self):
        if not self.isEnabled():
            return
        if self._popup is None:
            self._popup = _ModePopup(self._options, self)
            self._popup.picked.connect(self._on_picked)
            self._popup.closed.connect(self._on_closed)
        self._popup.set_selected(self._index)

        below = self._button.mapToGlobal(
            QPoint(0, self._button.height() + 6))
        above = self._button.mapToGlobal(QPoint(0, -6))
        self._popup.popup_at(below, above)
        self._button.set_open(True)

    def _on_picked(self, index):
        self._select(index)

    def _on_closed(self):
        self._button.set_open(False)

    def _close(self):
        if self._popup is not None and self._popup.isVisible():
            self._popup.close()
        self._button.set_open(False)


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
    'AboutDialog', 'Card', 'Divider', 'MetricChip', 'ModeSelect',
    'RichTextEdit', 'SegmentedControl', 'StepRow', 'app_icon',
    'default_font', 'logo_pixmap',
]
