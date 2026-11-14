# -*- coding: utf-8 -*-
"""占位符保护。

为什么需要这一层：降重是「中 → 英 → 德 → 日 → 葡 → 中」这样的翻译链，
每一跳都会把数字按目标语言的习惯重写。实测结果：

* 德语把 ``3.14%`` 写成 ``3,14 %``
* 葡语把 ``1200`` 写成 ``1.200``

这些改动在德语里是对的，但回译成中文后就变成错数据——论文里的小数点、
样本量、参考文献编号被悄悄改掉，用户根本看不出来。

做法：请求前把必须逐字节保留的片段换成 ``{0}`` ``{1}`` 这类占位符，
翻译完成后再换回原值。选这种格式是实测出来的——``{0}`` 能完整穿过 5 跳链路
（包括日语的重排），而 ``[[0]]`` 会被削成 ``[0]``、``§0§`` 会被插入空格、
Unicode 私有区字符会被直接吞掉。

换回时校验每个占位符恰好出现一次；一旦对不上就放弃本次保护结果，
让上层用原文重发一次。宁可多花一次额度，也不能把错数据交给用户。
"""

import re

#: 占位符模板，序号从 0 开始
TOKEN = '{{{}}}'

#: 顺序敏感：更具体的模式必须排在前面，否则会被宽松模式先吃掉。
_PATTERNS = (
    r'\[\s*\d+(?:\s*[,，、\-–—~]\s*\d+)*\s*\]',   # [12] [12,13] [12-15]
    r'\d+\.\d+\s*[%％]',                          # 3.14%
    r'\d+\s*[%％]',                               # 50%
    r'\d+\.\d+',                                  # 3.14
    r'(?<![\d.])\d{4,}(?![\d.])',                 # 1200 / 2024
)

_PROTECT_RE = re.compile('|'.join('(?:{})'.format(p) for p in _PATTERNS))

#: 原文本身含 ``{数字}`` 时不启用保护，避免与占位符混淆
_LOOKS_LIKE_TOKEN = re.compile(r'\{\s*\d+\s*\}')


def protect(text):
    """把需要保护的片段替换成占位符。

    Returns:
        ``(masked_text, mapping)``。没有可保护内容时返回 ``(text, {})``。
    """
    if not text or _LOOKS_LIKE_TOKEN.search(text):
        return text, {}

    mapping = {}

    def _replace(match):
        token = TOKEN.format(len(mapping))
        mapping[token] = match.group(0)
        return token

    masked = _PROTECT_RE.sub(_replace, text)
    return masked, mapping


def restore(text, mapping):
    """把占位符换回原值。

    Returns:
        还原后的文本；任一占位符丢失或重复时返回 ``None``，表示本次保护不可信。
    """
    if not mapping:
        return text

    for token in mapping:
        if text.count(token) != 1:
            return None

    for token, value in mapping.items():
        text = text.replace(token, value)
    return text


def count_protectable(text):
    """可保护片段数量，用于界面上的统计展示。"""
    if not text or _LOOKS_LIKE_TOKEN.search(text):
        return 0
    return len(_PROTECT_RE.findall(text))
