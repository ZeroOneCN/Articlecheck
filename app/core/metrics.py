# -*- coding: utf-8 -*-
"""文本改动度量。

旧实现有两个问题：

1. 用纯 Python 双层循环算编辑距离，6000 字约 3600 万次迭代，UI 直接冻住。
   这里优先用 rapidfuzz（C++ 实现），缺失时降级到 difflib 近似。

2. 把「编辑距离 / 原文长度」叫成「降重率」，还 ``min(..., 100)`` 把 >100% 抹平。
   它既不是查重率也不是重复率，只是**文本改动比例**。译文变长时分母用原文长度
   必然溢出，所以这里统一用 ``max(len_a, len_b)`` 归一化，并如实标注指标含义。
"""

try:
    from rapidfuzz.distance import Levenshtein as _Levenshtein

    _ENGINE = 'rapidfuzz'

    def _distance(a, b):
        return _Levenshtein.distance(a, b)

except ImportError:                                    # pragma: no cover
    from difflib import SequenceMatcher

    _ENGINE = 'difflib'

    def _distance(a, b):
        """近似编辑距离：用序列相似度反推。"""
        if not a and not b:
            return 0
        ratio = SequenceMatcher(None, a, b, autojunk=False).ratio()
        return round((1.0 - ratio) * max(len(a), len(b)))


def _normalize(text):
    """去掉所有空白，避免换行/缩进差异虚增改动量。"""
    return ''.join(text.split())


def compare(original, translated):
    """计算原文与译文的差异指标。

    返回 dict：
        distance      编辑距离
        changed_ratio 改动比例 0~1（越大改动越多）
        retention     保留比例 0~1
        len_before    原文长度
        len_after     译文长度
        engine        计算引擎
    """
    a = _normalize(original or '')
    b = _normalize(translated or '')

    if not a and not b:
        return {
            'distance': 0,
            'changed_ratio': 0.0,
            'retention': 0.0,
            'len_before': 0,
            'len_after': 0,
            'engine': _ENGINE,
        }

    distance = _distance(a, b)
    base = max(len(a), len(b), 1)
    changed = min(distance / base, 1.0)

    return {
        'distance': distance,
        'changed_ratio': changed,
        'retention': 1.0 - changed,
        # 字数报原始长度，与编辑框里的「字符」统计保持一致；
        # 距离计算仍用去空白的版本，避免换行/缩进虚增改动量。
        'len_before': len(original or ''),
        'len_after': len(translated or ''),
        'engine': _ENGINE,
    }


def format_report(report):
    """把指标格式化成一行给界面看。"""
    return (
        '改动 {:.1f}% · 保留 {:.1f}% · 字数 {} → {}'.format(
            report['changed_ratio'] * 100,
            report['retention'] * 100,
            report['len_before'],
            report['len_after'],
        )
    )
