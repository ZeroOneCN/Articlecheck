# -*- coding: utf-8 -*-
"""降重链路编排。

流程：按换行拆段 → 逐段翻译 → 用原始换行拼回。

两个关键点：

1. **每跳之后重新断句**。中文 1800 字约 5400 字节，译成英文可能变成 7000+
   字节；沿用上一跳的分段必然超限。所以每一跳都重新切块。

2. **保留段落结构**。旧版要求用户「请勿分段」，因为整段一起翻译会丢换行。
   现在逐段翻译，换行原样拼回，用户想分几段就分几段。
"""

from .errors import Cancelled, TranslationError
from .segmenter import MAX_QUERY_BYTES, plan_paragraph, split_paragraphs

#: 语言链路。键是界面上的模式名。
MODES = {
    '初级': ['zh', 'en', 'de', 'zh'],
    '中级': ['zh', 'en', 'de', 'jp', 'pt', 'zh'],
    '高级': ['zh', 'en', 'de', 'jp', 'pt', 'it', 'pl', 'bul', 'est', 'zh'],
}

#: 语言代码 -> 中文名，用于进度提示
LANG_NAMES = {
    'zh': '中文', 'en': '英语', 'de': '德语', 'jp': '日语', 'pt': '葡萄牙语',
    'it': '意大利语', 'pl': '波兰语', 'bul': '保加利亚语', 'est': '爱沙尼亚语',
}


def lang_label(code):
    return LANG_NAMES.get(code, code)


def estimate_requests(text, mode):
    """粗略估算请求数，用于提前提示额度消耗。"""
    chain = MODES.get(mode)
    if not chain:
        return 0
    hops = len(chain) - 1
    paragraphs = split_paragraphs(text)
    per_hop = sum(len(plan_paragraph(p)) for p in paragraphs)
    return per_hop * hops


def run(text, mode, translator, progress=None, should_cancel=None):
    """执行降重。

    Args:
        text: 原文，可含换行
        mode: ``MODES`` 里的模式名
        translator: ``BaiduTranslator`` 实例
        progress: 回调 ``(hop_index, hop_total, para_index, para_total,
                 seg_index, seg_total, from_lang, to_lang)``
        should_cancel: 返回 True 时尽快中止

    Returns:
        降重后的文本，段落结构与原文一致

    Raises:
        TranslationError: 链路不符 / 无可翻译内容
        Cancelled: 用户取消
    """
    chain = MODES.get(mode)
    if not chain:
        raise TranslationError('未知的降重模式：{}'.format(mode))

    paragraphs = split_paragraphs(text)
    if not paragraphs:
        raise TranslationError('没有可翻译的内容')

    hops = len(chain) - 1
    if hops <= 0:
        raise TranslationError('降重链路配置有误')

    def check_cancel():
        if should_cancel is not None and should_cancel():
            raise Cancelled('已取消')

    for hop in range(hops):
        from_lang, to_lang = chain[hop], chain[hop + 1]
        translated_paragraphs = []

        for para_index, paragraph in enumerate(paragraphs):
            check_cancel()
            # 每跳重新切块：上一跳的译文长度和断句位置都变了
            chunks = plan_paragraph(paragraph, MAX_QUERY_BYTES)
            pieces = []

            for seg_index, chunk in enumerate(chunks):
                check_cancel()
                if progress is not None:
                    progress(hop, hops, para_index, len(paragraphs),
                             seg_index, len(chunks), from_lang, to_lang)
                pieces.append(translator.translate(chunk, from_lang, to_lang))

            translated_paragraphs.append(''.join(pieces))

        paragraphs = translated_paragraphs

    return '\n'.join(paragraphs)


def percentage(hop, hops, para_index, para_total, seg_index, seg_total):
    """把分层进度折算成 0~100 的整数。"""
    if hops <= 0:
        return 0
    para_total = max(para_total, 1)
    seg_total = max(seg_total, 1)
    done = hop + ((para_index + (seg_index + 1) / seg_total) / para_total)
    return int(min(done / hops, 1.0) * 100)
