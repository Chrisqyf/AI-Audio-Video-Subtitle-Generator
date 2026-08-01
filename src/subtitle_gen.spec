# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置: 字幕生成 GUI + CLI 双模式单文件 EXE。

构建:  D:\Anaconda3\python.exe -m PyInstaller subtitle_gen.spec --clean
产物:  dist\subtitle_gen.exe  (单文件, 内嵌 ffmpeg)
"""
import os
import shutil

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# 关键依赖: 完整收集 aiohttp(C 扩展/数据) / certifi(cacert.pem) / dashscope
for pkg in ['aiohttp', 'certifi', 'dashscope']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 内嵌 ffmpeg / ffprobe (gyan.dev 静态构建, 无 DLL 依赖)。
# 查找顺序: 环境变量 FFMPEG_DIR > PATH 中的 ffmpeg 所在目录。
FFMPEG_DIR = os.environ.get('FFMPEG_DIR', '')
if not FFMPEG_DIR:
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        FFMPEG_DIR = os.path.dirname(ffmpeg_path)
if FFMPEG_DIR and os.path.exists(os.path.join(FFMPEG_DIR, 'ffmpeg.exe')):
    binaries += [
        (os.path.join(FFMPEG_DIR, 'ffmpeg.exe'), '.'),
        (os.path.join(FFMPEG_DIR, 'ffprobe.exe'), '.'),
    ]
else:
    print('WARNING: 未找到 ffmpeg (可用 FFMPEG_DIR 环境变量或加入 PATH)。'
          '将构建不含内嵌 ffmpeg 的 EXE (运行时需外部 ffmpeg)。')

a = Analysis(
    ['run_cli.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # 剔除与字幕生成无关的重依赖，控制体积
    excludes=[
        'streamlit', 'PIL', 'numpy', 'pandas', 'pyarrow', 'altair',
        'tornado', 'plotly', 'matplotlib', 'scipy', 'IPython',
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
    name='subtitle_gen',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # 保留控制台: CLI 模式输出; GUI 模式运行时自动隐藏
    disable_windowed_traceback=False,
    icon=None,
)
