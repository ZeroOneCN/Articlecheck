# -*- coding: utf-8 -*-
"""降重链路编排。

流程：按换行拆段 → 逐段翻译 → 用原始换行拼回。

三个关键点：

1. **每跳之后重新断句**。中文 1800 字约 5400 字节，译成英文可能变成 7000+
   字节；沿用上一跳的分段必然超限。所以每一跳都重新切块。

2. **保留段落结构**。旧版要求用户「请勿分段」，因为整段一起翻译会丢换行。
   现在逐段翻译，换行与空行原样拼回。

3. **逐块翻译才能命中缓存**。按块而不是按篇缓存，改一段只重翻那一段。
"""

from .errors import Cancelled, TranslationError
from .segmenter import MAX_QUERY_BYTES, plan_paragraph, split_paragraphs

#: 语言链路。键是界面上的模式名。
MODES = {
    '初级': ['zh', 'en', 'de', 'zh'],
    '中级': ['zh', 'en', 'de', 'jp', 'pt', 'zh'],
    '高级': ['zh', 'en', 'de', 'jp', 'pt', 'it', 'pl', 'bul', 'est', 'zh'],
}

#: 模式的一句话说明，用于界面展示
MODE_DESC = {
    '初级': '中 → 英 → 德 → 中',
    '中级': '中 → 英 → 德 → 日 → 葡 → 中',
    '高级': '中 → 英 → 德 → 日 → 葡 → 意 → 波 → 保 → 爱 → 中',
}

#: 语言代码 -> 中文名，用于进度提示
LANG_NAMES = {
    'zh': '中文', 'en': '英语', 'de': '德语', 'jp': '日语', 'pt': '葡萄牙语',
    'it': '意大利语', 'pl': '波兰语', 'bul': '保加利亚语', 'est': '爱沙尼亚语',
}


def lang_label(code):
    return LANG_NAMES.get(code, code)


def hop_count(mode):
    chain = MODES.get(mode) or []
    return max(len(chain) - 1, 0)


def estimate_requests(text, mode):
    """粗略估算请求数，用于提前提示额度消耗。"""
    hops = hop_count(mode)
    if not hops:
        return 0
    per_hop = sum(len(plan_paragraph(p)) for p in split_paragraphs(text))
    return per_hop * hops


def estimate_chars(text, mode):
    """估算字符额度消耗：正文字数 × 跳数。"""
    return len(text or '') * hop_count(mode)


def run(text, mode, translator, progress=None, should_cancel=None):
    """执行降重。

    Args:
        text: 原文，可含换行与空行
        mode: ``MODES`` 里的模式名
        translator: ``BaiduTranslator`` 实例
        progress: 回调 ``(hop_index, hop_total, para_index, para_total,
                 seg_index, seg_total, from_lang, to_lang)``
        should_cancel: 返回 True 时尽快中止

    Returns:
        降重后的文本，段落结构与原文一致（含空行）

    Raises:
        TranslationError: 链路不符 / 无可翻译内容
        Cancelled: 用户取消
    """
    chain = MODES.get(mode)
    if not chain:
        raise TranslationError('未知的降重模式：{}'.format(mode))

    hops = len(chain) - 1
    if hops <= 0:
        raise TranslationError('降重链路配置有误')

    #: 保留空行的段落列表。空行不送翻译，只占位。
    paragraphs = [line.strip() for line in (text or '').split('\n')]
    total = sum(1 for line in paragraphs if line)
    if not total:
        raise TranslationError('没有可翻译的内容')

    def check_cancel():
        if should_cancel is not None and should_cancel():
            raise Cancelled('已取消')

    for hop in range(hops):
        from_lang, to_lang = chain[hop], chain[hop + 1]
        translated = []

        for para_index, paragraph in enumerate(paragraphs):
            check_cancel()
            if not paragraph:
                translated.append('')
                continue

            # 每跳重新切块：上一跳的译文长度和断句位置都变了
            chunks = plan_paragraph(paragraph, MAX_QUERY_BYTES)
            pieces = []

            for seg_index, chunk in enumerate(chunks):
                check_cancel()
                if progress is not None:
                    progress(hop, hops, para_index, len(paragraphs),
                             seg_index, len(chunks), from_lang, to_lang)
                pieces.append(translator.translate(chunk, from_lang, to_lang))

            translated.append(''.join(pieces))

        paragraphs = translated

    return '\n'.join(paragraphs)


def percentage(hop, hops, para_index, para_total, seg_index, seg_total):
    """把分层进度折算成 0~100 的整数。"""
    if hops <= 0:
        return 0
    para_total = max(para_total, 1)
    seg_total = max(seg_total, 1)
    done = hop + ((para_index + (seg_index + 1) / seg_total) / para_total)
    return int(min(done / hops, 1.0) * 100)
