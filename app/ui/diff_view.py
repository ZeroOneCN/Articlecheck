# -*- coding: utf-8 -*-
"""文本对比视图。

v1 用 ``text.splitlines()`` 逐行 diff，而使用说明又要求用户「请勿分段」——
单段落没有换行，``splitlines()`` 只返回 1 行，diff 结果就是「整段删 + 整段增」，
红绿各半，等于没对比。

现在：先按句子切分做块级比对，差异块内部再做字符级高亮，
删除部分加删除线，避免红绿混排后读起来像口吃。
"""

import difflib
import re

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTextBlockFormat, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget

from . import theme

#: 句子边界（含换行），切分后保留分隔符
_UNIT = re.compile(r'(?<=[。！？；!?;])|(?<=\.)(?=\s)|(?<=\n)')


def split_units(text):
    return [unit for unit in _UNIT.split(text or '') if unit]


class DiffView(QWidget):
    """行内差异：红色删除线为删除，绿色为新增。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(self._swatch('#F7C6C0'))
        header.addWidget(self._legend_text('删除（带删除线）'))
        header.addSpacing(6)
        header.addWidget(self._swatch('#BCE6D3'))
        header.addWidget(self._legend_text('新增'))
        header.addStretch()

        self.summary_label = QLabel('按句比对，差异标到字')
        self.summary_label.setObjectName('Muted')
        header.addWidget(self.summary_label)
        layout.addLayout(header)

        self.diff_text = QTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_text.setPlaceholderText('降重完成后，这里按句展示原文与结果的差异。')
        self.diff_text.setStyleSheet(
            'QTextEdit {{ font-family: {}; font-size: {}px; '
            'background: {}; }}'.format(
                theme.FONT_BODY, theme.EDITOR_PX, theme.COLORS['surface'])
        )
        layout.addWidget(self.diff_text, 1)

        self._normal = QTextCharFormat()
        self._normal.setForeground(QColor(theme.COLORS['text']))

        self._removed = QTextCharFormat()
        self._removed.setBackground(QColor(theme.COLORS['danger_soft']))
        self._removed.setForeground(QColor(theme.COLORS['danger']))
        # 加删除线，否则删除与新增混排后整句读起来像口吃
        self._removed.setFontStrikeOut(True)

        self._added = QTextCharFormat()
        self._added.setBackground(QColor(theme.COLORS['success_soft']))
        self._added.setForeground(QColor(theme.COLORS['success']))

        self._block = QTextBlockFormat()
        self._block.setAlignment(Qt.AlignJustify)
        self._block.setTextIndent(
            self.diff_text.fontMetrics().horizontalAdvance('中') * 2
        )
        self._block.setLineHeight(180, QTextBlockFormat.ProportionalHeight)

    @staticmethod
    def _swatch(color):
        """图例色块。用固定尺寸的 QLabel，比在富文本里塞 &nbsp; 更可控。"""
        swatch = QLabel()
        swatch.setFixedSize(12, 12)
        swatch.setStyleSheet(
            'background: {}; border-radius: 3px;'.format(color))
        return swatch

    @staticmethod
    def _legend_text(text):
        label = QLabel(text)
        label.setStyleSheet('color: {}; font-size: 13px;'.format(
            theme.COLORS['muted']))
        return label

    # ── 渲染 ──────────────────────────────────────────────
    def _insert(self, cursor, text, char_format):
        if not text:
            return
        segments = text.split('\n')
        for index, segment in enumerate(segments):
            if index > 0:
                cursor.insertBlock(self._block)
            if segment:
                cursor.insertText(segment, char_format)

    def _insert_replace(self, cursor, old, new):
        """差异块内部做字符级比对。"""
        matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                self._insert(cursor, old[i1:i2], self._normal)
            else:
                self._insert(cursor, old[i1:i2], self._removed)
                self._insert(cursor, new[j1:j2], self._added)

    def show_diff(self, original, translated):
        self.diff_text.clear()
        cursor = self.diff_text.textCursor()
        cursor.setBlockFormat(self._block)

        left = split_units(original)
        right = split_units(translated)
        changed = 0

        matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                self._insert(cursor, ''.join(left[i1:i2]), self._normal)
            elif tag == 'delete':
                changed += 1
                self._insert(cursor, ''.join(left[i1:i2]), self._removed)
            elif tag == 'insert':
                changed += 1
                self._insert(cursor, ''.join(right[j1:j2]), self._added)
            else:                                       # replace
                changed += 1
                self._insert_replace(
                    cursor, ''.join(left[i1:i2]), ''.join(right[j1:j2])
                )

        self.diff_text.moveCursor(QTextCursor.Start)
        self.summary_label.setText(
            '共 {} 处句式改动 · 按句比对，差异标到字'.format(changed)
            if changed else '未检测到句式改动'
        )

    def clear(self):
        self.diff_text.clear()
        self.summary_label.setText('按句比对，差异标到字')
