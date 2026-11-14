# -*- coding: utf-8 -*-
"""导出降重结果。

论文场景基本只要两种格式：``.txt``（丢进任何地方都能看）和 ``.docx``
（直接接着排版）。``python-docx`` 缺失时自动降级为 txt，不影响主流程。
"""

from pathlib import Path

#: 导出的 Word 排版参数：宋体小四、首行缩进两字、1.5 倍行距
DOCX_FONT = '宋体'
DOCX_SIZE_PT = 12
DOCX_LINE_SPACING = 1.5


def docx_available():
    try:
        import docx  # noqa: F401
        return True
    except ImportError:
        return False


def _split(text):
    return [line.strip() for line in (text or '').split('\n') if line.strip()]


def to_txt(text, path):
    """写纯文本。用 ``utf-8-sig``，Windows 记事本打开不会乱码。"""
    Path(path).write_text(text or '', encoding='utf-8-sig')
    return path


def to_docx(text, path, title=None, source=None):
    """写 Word 文档。

    Args:
        text: 降重后的正文，按换行分段
        path: 输出路径
        title: 可选标题
        source: 可选原文，提供时附在文末供对照

    Raises:
        ImportError: 未安装 python-docx
    """
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Pt

    document = Document()

    normal = document.styles['Normal']
    normal.font.name = DOCX_FONT
    normal.font.size = Pt(DOCX_SIZE_PT)
    normal.element.rPr.rFonts.set(qn('w:eastAsia'), DOCX_FONT)

    if title:
        heading = document.add_paragraph()
        run = heading.add_run(title)
        run.bold = True
        run.font.size = Pt(16)
        run.font.name = '黑体'
        run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for line in _split(text):
        paragraph = document.add_paragraph(line)
        fmt = paragraph.paragraph_format
        fmt.first_line_indent = Pt(DOCX_SIZE_PT * 2)      # 首行缩进两个字符
        fmt.line_spacing = DOCX_LINE_SPACING
        fmt.space_after = Pt(0)

    if source and source.strip():
        document.add_page_break()
        label = document.add_paragraph()
        label_run = label.add_run('附：原文')
        label_run.bold = True
        for line in _split(source):
            paragraph = document.add_paragraph(line)
            fmt = paragraph.paragraph_format
            fmt.first_line_indent = Pt(DOCX_SIZE_PT * 2)
            fmt.line_spacing = DOCX_LINE_SPACING
            fmt.space_after = Pt(0)

    document.save(str(path))
    return path


def save(text, path, source=None, title=None):
    """按扩展名选择格式。"""
    suffix = Path(path).suffix.lower()
    if suffix == '.docx':
        return to_docx(text, path, title=title, source=source)
    return to_txt(text, path)
