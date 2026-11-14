# -*- coding: utf-8 -*-
"""从 icon.svg 生成 Windows ICO 与多尺寸 PNG。

图标是纯矢量路径，用 QtSvg 逐尺寸渲染，比「渲染 256 再缩小」在小尺寸下清晰得多。

用法：
    python tools/make_icons.py
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QByteArray, QBuffer, QIODevice, Qt   # noqa: E402
from PyQt5.QtGui import QGuiApplication, QImage, QPainter     # noqa: E402
from PyQt5.QtSvg import QSvgRenderer                           # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / 'app' / 'resources'
SVG_PATH = RESOURCES / 'icon.svg'

#: ICO 内嵌的尺寸。20/40 是 125% / 200% 缩放下的常用尺寸。
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
PNG_SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(svg, size):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHints(
        QPainter.Antialiasing
        | QPainter.SmoothPixmapTransform
        | QPainter.TextAntialiasing
    )
    svg.render(painter)
    painter.end()
    return img


def png_bytes(img):
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    img.save(buffer, 'PNG')
    data = bytes(buffer.data())
    buffer.close()
    return data


def write_ico(frames, path):
    """按 ICO 规范拼装，每一帧都放 PNG 数据（Vista+ 原生支持）。"""
    count = len(frames)
    header = struct.pack('<HHH', 0, 1, count)
    entries = b''
    payload = b''
    offset = 6 + 16 * count

    for size, data in frames:
        edge = 0 if size >= 256 else size          # 256 在规范里记 0
        entries += struct.pack('<BBBBHHII', edge, edge, 0, 0, 1, 32,
                               len(data), offset)
        payload += data
        offset += len(data)

    path.write_bytes(header + entries + payload)


def main():
    if not SVG_PATH.exists():
        sys.exit('缺少 {}'.format(SVG_PATH))

    app = QGuiApplication(sys.argv)          # noqa: F841  QImage/QPainter 需要
    svg = QSvgRenderer(QByteArray(SVG_PATH.read_bytes()))
    if not svg.isValid():
        sys.exit('SVG 解析失败：{}'.format(SVG_PATH))

    frames = []
    for size in ICO_SIZES:
        img = render(svg, size)
        if size in PNG_SIZES:
            img.save(str(RESOURCES / 'icon_{}.png'.format(size)), 'PNG')
        frames.append((size, png_bytes(img)))

    write_ico(frames, RESOURCES / 'icon.ico')

    print('已生成 icon.ico  {} 尺寸: {}'.format(
        (RESOURCES / 'icon.ico').stat().st_size, ICO_SIZES))
    print('已生成 PNG: {}'.format(', '.join('icon_{}.png'.format(s) for s in PNG_SIZES)))


if __name__ == '__main__':
    main()
