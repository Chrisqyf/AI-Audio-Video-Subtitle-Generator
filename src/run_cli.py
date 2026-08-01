#!/usr/bin/env python3
"""字幕生成 EXE 入口：无参数 → 启动 GUI；有参数 → 走 CLI。

也是 PyInstaller 的入口脚本。冻结模式下负责:
1. 将内嵌的 ffmpeg/ffprobe 解包目录加入 PATH（subprocess 才能找到）。
2. 清空 DEFAULT_API_KEY，强制运行时读取 Key（EXE 内不写死 Key）。

CLI 契约（供未来 Node 本地 EXE 自动调用）:
    subtitle_gen.exe <video> [--offline] [--lang en|zh] [--model M] [-o out.srt]
                       [--keep-wav] [--timeout T] [--key-file F] [--check]
    Key 来源: --api-key / 环境变量 DASHSCOPE_API_KEY / subtitle_key.txt
"""
import os
import sys


def _setup_frozen():
    """冻结模式 (PyInstaller onefile) 下，把内嵌的 ffmpeg/ffprobe 目录加入 PATH。"""
    if not getattr(sys, 'frozen', False):
        return
    meipass = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    if os.path.isdir(meipass) and os.path.exists(os.path.join(meipass, 'ffmpeg.exe')):
        os.environ['PATH'] = meipass + os.pathsep + os.environ.get('PATH', '')


def _hide_console():
    """GUI 模式下隐藏 Windows 控制台窗口。"""
    if sys.platform == 'win32':
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        except Exception:
            pass


def main():
    # 必须最先执行: 保证后续 subprocess 能找到内嵌的 ffmpeg
    _setup_frozen()

    # 确保能导入同目录模块
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_local
    # 强制运行时 Key 策略: EXE 内不写死 Key
    test_local.DEFAULT_API_KEY = ''

    if len(sys.argv) <= 1:
        # 无参数 → 图形界面
        _hide_console()
        import gui
        return gui.main()
    else:
        # 有参数 → 命令行 (test_local.main 内部 sys.exit)
        return test_local.main()


if __name__ == '__main__':
    sys.exit(main())
