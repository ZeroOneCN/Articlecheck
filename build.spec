# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

构建：
    python -m PyInstaller build.spec --noconfirm --clean

产物：dist/ArticleReducer.exe（单文件，双击即用，无需安装 Python）
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # 图标与 SVG 必须一起打进去，否则窗口/任务栏无图标
    datas=[('app/resources', 'app/resources')],
    hiddenimports=['PyQt5.QtSvg'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 排除与功能无关的重型库，能把体积砍掉一截
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
        'PIL', 'IPython', 'notebook', 'pytest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ArticleReducer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                  # 双击不弹黑框
    disable_windowed_traceback=False,
    icon='app/resources/icon.ico',
    version='tools/version_info.txt',
)
