# -*- coding: utf-8 -*-
"""文本断句与分段。

修掉的两个老问题：

1. 旧实现 ``text.split('。')`` 只认中文句号。可降重链路是
   ``中 -> 英 -> 德 -> …``，从第二步起文本就是英文了，一个「。」都没有，
   于是整块文本被当成一个 segment。

2. 旧实现按「字符」计量，而百度翻译的硬约束是 **6000 字节**。
   6000 个汉字 = 18000 字节，超出 3 倍。现在统一按 UTF-8 字节计量。
"""

import re

#: 单次请求的字节上限。百度硬限制 6000 字节，留 400 字节余量给其它参数。
MAX_QUERY_BYTES = 5600

#: 句末标点：中日文一套、拉丁一套。英文的 "." 只在后接空白或行尾时才算句末，
#: 这样 3.14、v2.0.1、e.g 之类不会被误切。
_SENTENCE_END = re.compile(r'[。！？；!?;]|\.(?=\s|$)')

#: 标点后紧跟的收尾符号，应当并入当前句，不要留给下一句。
_TRAILING = ' \t）)」』"”\''


def byte_len(text):
    """UTF-8 字节数。百度按字节算，不是按字符算。"""
    return len(text.encode('utf-8'))


def _char_bytes(ch):
    """单个字符的 UTF-8 字节数，避免反复 encode 造成 O(n^2)。"""
    code = ord(ch)
    if code < 0x80:
        return 1
    if code < 0x800:
        return 2
    if code < 0x10000:
        return 3
    return 4


def split_sentences(text):
    """按句末标点切句，保留标点与收尾符号。"""
    sentences = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        while end < len(text) and text[end] in _TRAILING:
            end += 1
        sentences.append(text[start:end])
        start = end
    if start < len(text):
        sentences.append(text[start:])
    return [s for s in sentences if s.strip()]


def hard_split(text, limit=MAX_QUERY_BYTES):
    """按字节硬切。

    用于「单个句子本身就超长」的情况（英文长句、无标点列表）。
    旧实现对这种情况直接塞进去，导致 54005 报错。
    """
    parts = []
    buf = []
    size = 0
    for ch in text:
        n = _char_bytes(ch)
        if size + n > limit and buf:
            parts.append(''.join(buf))
            buf = []
            size = 0
        buf.append(ch)
        size += n
    if buf:
        parts.append(''.join(buf))
    return parts


def pack(sentences, limit=MAX_QUERY_BYTES):
    """把句子贪心装箱成若干不超过 limit 字节的段落块。"""
    chunks = []
    buf = []
    size = 0
    for sentence in sentences:
        n = byte_len(sentence)
        if n > limit:                      # 单句超长：先落盘再硬切
            if buf:
                chunks.append(''.join(buf))
                buf = []
                size = 0
            chunks.extend(hard_split(sentence, limit))
            continue
        if size + n > limit:               # 装不下：换箱
            chunks.append(''.join(buf))
            buf = [sentence]
            size = n
        else:
            buf.append(sentence)
            size += n
    if buf:
        chunks.append(''.join(buf))
    return chunks


def split_paragraphs(text):
    """按换行拆段，丢弃空行。"""
    return [p.strip() for p in text.split('\n') if p.strip()]


def plan_paragraph(paragraph, limit=MAX_QUERY_BYTES):
    """把一段文本切成可直接发请求的块列表。"""
    return pack(split_sentences(paragraph), limit)
