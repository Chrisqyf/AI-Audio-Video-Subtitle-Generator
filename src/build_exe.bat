@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== 构建字幕生成独立 EXE =====
echo 前置要求: 已安装 Python 3.9+ 与 dashscope/streamlit 等依赖; ffmpeg 在 PATH 或设置 FFMPEG_DIR
echo.

echo [1/2] 安装 PyInstaller ...
python -m pip install pyinstaller || goto :err

echo [2/2] 构建 subtitle_gen.exe (可能需要几分钟) ...
python -m PyInstaller subtitle_gen.spec --clean --noconfirm || goto :err

echo.
echo ===== 构建完成: dist\subtitle_gen.exe =====
echo 用法:
echo   dist\subtitle_gen.exe                    双击 → GUI
echo   dist\subtitle_gen.exe 视频.mp4 --lang en 命令行(默认自动: 实时优先)
echo API Key: 设置环境变量 DASHSCOPE_API_KEY 或放 subtitle_key.txt 在 exe 同目录
pause
exit /b 0

:err
echo 构建失败，请检查上方错误信息。
pause
exit /b 1
