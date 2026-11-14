# -*- coding: utf-8 -*-
"""离线自检。

不联网、不写用户配置，全部在临时目录里跑：

    python tests/run_tests.py

覆盖范围：断句与字节限制、占位符保护（含失效降级）、缓存、链路编排、
导出、指标、以及界面构造与关键状态。
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 隔离用户目录，避免测试污染真实配置
_TMP = Path(tempfile.mkdtemp(prefix='articlereducer_test_'))
os.environ['APPDATA'] = str(_TMP)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

PASSED = []
FAILED = []


def check(name, condition, detail=''):
    if condition:
        PASSED.append(name)
        print('  ✓', name)
    else:
        FAILED.append(name)
        print('  ✗', name, '' if not detail else '-> {}'.format(detail))


# ── 断句与分段 ────────────────────────────────────────────
def test_segmenter():
    from app.core import segmenter as sg

    print('\n[断句 / 字节]')
    check('UTF-8 字节数按中文 3 字节算', sg.byte_len('中文') == 6,
          sg.byte_len('中文'))

    zh = '第一句。第二句！第三句？'
    check('中文按句末标点切分', len(sg.split_sentences(zh)) == 3,
          sg.split_sentences(zh))

    en = 'First sentence. Second one! Third?'
    check('英文按 . ! ? 切分', len(sg.split_sentences(en)) == 3,
          sg.split_sentences(en))

    check('小数点不误切', len(sg.split_sentences('v2.0.1 是版本号。')) == 1,
          sg.split_sentences('v2.0.1 是版本号。'))

    long_text = '无标点长文' * 1200          # 6000 汉字 = 18000 字节
    chunks = sg.hard_split(long_text, 5600)
    check('超长无标点文本被硬切', len(chunks) >= 3, len(chunks))
    check('每块不超过 5600 字节',
          all(sg.byte_len(c) <= 5600 for c in chunks),
          [sg.byte_len(c) for c in chunks])

    packed = sg.pack(sg.split_sentences('句子。' * 3000), 5600)
    check('装箱后每块不超限', all(sg.byte_len(c) <= 5600 for c in packed),
          max(sg.byte_len(c) for c in packed))


# ── 占位符保护 ────────────────────────────────────────────
def test_protect():
    from app.core import protect

    print('\n[占位符保护]')
    text = '准确率为 3.14%，共 1200 个样本，见文献[12]与[13-15]。'
    masked, mapping = protect.protect(text)
    check('数字与引用被替换', '{0}' in masked and '{2}' in masked, masked)
    check('占位符数量正确', len(mapping) >= 4, mapping)
    check('还原结果与原文一致', protect.restore(masked, mapping) == text,
          protect.restore(masked, mapping))

    untouchable, empty = protect.protect('这段没有数字。')
    check('无数字时不产生占位符', not empty and untouchable == '这段没有数字。')

    collision, empty2 = protect.protect('公式 {0} 已存在。')
    check('原文自带 {0} 时放弃保护', not empty2 and collision == '公式 {0} 已存在。')

    check('占位符丢失时返回 None',
          protect.restore('差值为，参考。', mapping) is None)
    check('占位符重复时返回 None',
          protect.restore(masked + masked, mapping) is None)


# ── 缓存 ──────────────────────────────────────────────────
def test_cache():
    from app.core.cache import TranslationCache

    print('\n[缓存]')
    path = _TMP / 'test_cache.db'
    cache = TranslationCache(path=path)

    cache.put('原文', 'zh', 'en', 'source')
    check('写入后可命中', cache.get('原文', 'zh', 'en') == 'source')

    check('语言方向影响键',
          cache.get('原文', 'zh', 'de') is None)

    count, size = cache.stats()
    check('统计条目数', count == 1, (count, size))

    removed = cache.clear()
    check('清空缓存', removed == 1 and cache.get('原文', 'zh', 'en') is None)

    disabled = TranslationCache(path=_TMP / 'off.db', enabled=False)
    disabled.put('a', 'zh', 'en', 'b')
    check('关闭后不写入', disabled.get('a', 'zh', 'en') is None)


# ── 链路编排 ──────────────────────────────────────────────
class FakeTranslator:
    """离线替身：只做可预测的字符替换，便于断言。"""

    def __init__(self, drop_token=False):
        self.calls = 0
        self.drop_token = drop_token
        from app.core.translator import TranslationStats
        self.stats = TranslationStats()

    def translate(self, text, from_lang, to_lang, **kwargs):
        self.calls += 1
        if self.drop_token:
            return text.replace('{', '').replace('}', '')
        return text


def test_pipeline():
    from app.core import pipeline
    from app.core.errors import Cancelled, TranslationError

    print('\n[链路编排]')
    text = '第一段第一句。第一段第二句。\n\n第二段。'
    fake = FakeTranslator()
    result = pipeline.run(text, '初级', fake)

    check('空行被保留', result.count('\n') == text.count('\n'), repr(result))
    check('段落数一致', len(result.split('\n')) == len(text.split('\n')))
    # 非空段落 2 个 × 3 跳
    check('每跳都调用翻译器',
          fake.calls == 2 * pipeline.hop_count('初级'), fake.calls)

    try:
        pipeline.run('内容。', '不存在的模式', fake)
        check('未知模式抛异常', False)
    except TranslationError:
        check('未知模式抛异常', True)

    cancelled = {'flag': False}

    def should_cancel():
        return cancelled['flag']

    class CancelAfterOne(FakeTranslator):
        def translate(self, text, from_lang, to_lang, **kwargs):
            cancelled['flag'] = True
            return text

    try:
        pipeline.run('句子。', '高级', CancelAfterOne(),
                     should_cancel=should_cancel)
        check('取消能中断链路', False)
    except Cancelled:
        check('取消能中断链路', True)

    check('额度估算 = 字数 × 跳数',
          pipeline.estimate_chars('12345', '初级') == 5 * 3,
          pipeline.estimate_chars('12345', '初级'))


# ── 翻译器：保护与缓存集成 ────────────────────────────────
def test_translator_protection():
    from app.core.cache import TranslationCache
    from app.core.translator import BaiduTranslator

    print('\n[翻译器：保护 / 缓存]')

    cache = TranslationCache(path=_TMP / 'tr.db')
    translator = BaiduTranslator('id', 'key', cache=cache)

    sent = []

    def fake_request(text, from_lang, to_lang):
        sent.append(text)
        # 模拟德语把 3.14 写成 3,14 的行为
        return text.replace('3.14', '3,14').replace('{', '{')

    translator._request = fake_request
    out = translator.translate('准确率为 3.14%。', 'zh', 'de')

    check('占位符保护后数字未被改写', '3.14' in out and '3,14' not in out, out)
    check('发出的是被保护的文本', '{0}' in sent[0], sent[0])

    # 缓存命中：同样的输入不再发请求
    before = len(sent)
    translator.translate('准确率为 3.14%。', 'zh', 'de')
    check('第二次命中缓存不发请求', len(sent) == before, len(sent))
    check('缓存节省字符数被记录', translator.stats.cache_hits == 1,
          translator.stats.as_dict())

    # 占位符被吞：应放弃本次结果并重发原文
    sent2 = []

    def dropping_request(text, from_lang, to_lang):
        sent2.append(text)
        return text.replace('{0}', '').replace('{', '').replace('}', '')

    translator2 = BaiduTranslator('id', 'key')
    translator2._request = dropping_request
    out2 = translator2.translate('准确率为 3.14%。', 'zh', 'de')

    check('保护失效时重发原文', len(sent2) == 2, sent2)
    check('降级次数被记录', translator2.stats.protection_fallbacks == 1,
          translator2.stats.as_dict())
    check('降级结果不含残缺占位符', '{' not in out2, out2)


# ── 导出 ──────────────────────────────────────────────────
def test_export():
    from app.core import export

    print('\n[导出]')
    text = '第一段内容。\n\n第二段内容。'

    txt = export.to_txt(text, _TMP / 'out.txt')
    raw = Path(txt).read_bytes()
    check('txt 使用 utf-8-sig', raw.startswith(b'\xef\xbb\xbf'))
    check('txt 内容完整', Path(txt).read_text(encoding='utf-8-sig') == text)

    if not export.docx_available():
        check('docx 依赖可用', False, '未安装 python-docx')
        return

    docx_path = export.to_docx(text, _TMP / 'out.docx', title='降重结果',
                              source='原文内容。')
    check('docx 已生成', Path(docx_path).exists()
          and Path(docx_path).stat().st_size > 5000,
          Path(docx_path).stat().st_size if Path(docx_path).exists() else 0)

    from docx import Document
    paragraphs = [p.text for p in Document(str(docx_path)).paragraphs if p.text]
    check('docx 段落与原文对应',
          '第一段内容。' in paragraphs and '第二段内容。' in paragraphs,
          paragraphs[:6])


# ── 指标 ──────────────────────────────────────────────────
def test_metrics():
    from app.core import metrics

    print('\n[指标]')
    report = metrics.compare('完全相同的内容。', '完全相同的内容。')
    check('相同文本改动率为 0', report['changed_ratio'] == 0, report)

    report = metrics.compare('完全不同的内容。', '另一段话。')
    check('改动率在 0~1 之间', 0 <= report['changed_ratio'] <= 1, report)
    check('保留率与改动率互补',
          abs(report['changed_ratio'] + report['retention'] - 1) < 1e-9)
    check('长译文不会溢出 100%', report['changed_ratio'] <= 1.0)


# ── 界面 ──────────────────────────────────────────────────
def test_ui():
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    from app.ui import theme
    from app.ui.main_window import MainWindow
    from app.ui.widgets import default_font

    print('\n[界面]')
    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(default_font())
    theme.apply(app)

    window = MainWindow()
    window.show()
    QTest.qWait(400)

    check('窗口标题含版本号', 'v2.0.0' in window.windowTitle(),
          window.windowTitle())
    check('窗口有图标', not window.windowIcon().isNull())

    window.input_text.set_text('第一段。\n\n第二段。')
    QTest.qWait(50)
    check('字数统计改报段落数', '段落 2' in window.input_counter.text(),
          window.input_counter.text())

    window._update_estimate()
    check('有内容时显示预估', window.estimate_label.text() != '',
          window.estimate_label.text())

    window._refresh_credential_status()
    check('未配置时给出提示', '尚未配置' in window.cred_label.text(),
          window.cred_label.text())

    # 走真实路径：填输入框 → 同步凭证 → 刷新状态（跳过会弹窗的保存动作）
    window.appid_edit.setText('20250000000000000')
    window.appkey_edit.setText('k' * 24)
    check('凭证同步成功', window._sync_credentials())
    window._refresh_credential_status()
    check('配置后状态变为就绪', '就绪' in window.cred_label.text(),
          window.cred_label.text())
    check('凭证已注入翻译器', window.translator.has_credentials())

    window.diff_view.show_diff('原文一句话。第二句。', '改写的句子。第二句。')
    check('对比视图有内容', len(window.diff_view.diff_text.toPlainText()) > 0)

    window.diff_view.clear()
    check('对比视图可清空',
          window.diff_view.diff_text.toPlainText() == '')

    check('缓存提示已渲染', '缓存' in window.cache_label.text(),
          window.cache_label.text())

    # 启动引导里的异常钩子：打包后崩溃过一次（函数内漏 import sys），
    # 这里必须真的调用一次，否则测试永远发现不了
    from app.ui.main_window import _install_excepthook
    original_hook = sys.excepthook
    _install_excepthook()
    check('异常钩子安装成功', sys.excepthook is not original_hook)
    sys.excepthook = original_hook

    check('图标资源存在',
          (ROOT / 'app' / 'resources' / 'icon.ico').exists())
    check('ICO 含多尺寸', (ROOT / 'app' / 'resources' / 'icon.ico')
          .stat().st_size > 10000)

    # 弹窗只在点了才构造，很容易藏住「样式串花括号」这类错误
    from app.ui.widgets import AboutDialog
    about = AboutDialog()
    check('关于窗口可构造', about.width() > 300, about.width())
    about.close()

    window.close()


def main():
    try:
        test_segmenter()
        test_protect()
        test_cache()
        test_pipeline()
        test_translator_protection()
        test_export()
        test_metrics()
        test_ui()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)

    total = len(PASSED) + len(FAILED)
    print('\n' + '─' * 46)
    print('通过 {} / {}'.format(len(PASSED), total))
    if FAILED:
        print('失败项：')
        for name in FAILED:
            print('  -', name)
        return 1
    print('全部通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
