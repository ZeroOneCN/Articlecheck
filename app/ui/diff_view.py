# -*- coding: utf-8 -*-
"""文本对比视图。

旧实现：``text.splitlines()`` 逐行 diff。可使用说明又要求用户「请勿分段」——
单段落没有换行，``splitlines()`` 只返回 1 行，diff 结果就是「整段删 + 整段增」，
红绿各半，等于没对比。

现在：先按句子切分做块级比对，差异块内部再做字符级高亮。
"""

import difflib
import re

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTextBlockFormat, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

#: 句子边界（含换行），切分后保留分隔符
_UNIT = re.compile(r'(?<=[。！？；!?;])|(?<=\.)(?=\s)|(?<=\n)')


def split_units(text):
    return [unit for unit in _UNIT.split(text or '') if unit]


class DiffView(QWidget):
    """左右差异以行内高亮呈现：红色为删除，绿色为新增。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        legend = QLabel(
            '<span style="background:#ffd9d9;">&nbsp;&nbsp;&nbsp;</span> 删除（带删除线）'
            '&nbsp;&nbsp;&nbsp;'
            '<span style="background:#d9f5d9;">&nbsp;&nbsp;&nbsp;</span> 新增'
            '&nbsp;&nbsp;&nbsp;<span style="color:#888;">按句比对，差异处标到字</span>'
        )
        layout.addWidget(legend)

        self.diff_text = QTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_text.setStyleSheet(
            'QTextEdit { font-family: "宋体", "SimSun", "Songti SC", serif; '
            'font-size: 12pt; }'
        )
        layout.addWidget(self.diff_text)

        self._normal = QTextCharFormat()
        self._normal.setBackground(QColor('#ffffff'))

        self._removed = QTextCharFormat()
        self._removed.setBackground(QColor('#ffd9d9'))
        # 加删除线，否则删除与新增混排后整句读起来像口吃
        self._removed.setFontStrikeOut(True)

        self._added = QTextCharFormat()
        self._added.setBackground(QColor('#d9f5d9'))

        self._block = QTextBlockFormat()
        self._block.setAlignment(Qt.AlignJustify)
        self._block.setTextIndent(24)

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

        matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                self._insert(cursor, ''.join(left[i1:i2]), self._normal)
            elif tag == 'delete':
                self._insert(cursor, ''.join(left[i1:i2]), self._removed)
            elif tag == 'insert':
                self._insert(cursor, ''.join(right[j1:j2]), self._added)
            else:                                       # replace
                self._insert_replace(
                    cursor, ''.join(left[i1:i2]), ''.join(right[j1:j2])
                )

        self.diff_text.moveCursor(QTextCursor.Start)

    def clear(self):
        self.diff_text.clear()
