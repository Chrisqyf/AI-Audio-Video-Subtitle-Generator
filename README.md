# 🎙️ AI 字幕生成器（独立 EXE）

基于阿里云 DashScope 语音大模型（Qwen/Paraformer）的**音视频字幕生成工具**，打包为单文件 Windows EXE，**无需安装 Python / ffmpeg / 任何依赖**，双击即用。

支持从视频中自动提取音频，AI 只处理音频，生成带时间戳的 **SRT 字幕**，并支持语言统一（英文/中文）输出。

---

## ✨ 功能特性

- 🎬 **视频→字幕**：自动用 ffmpeg 提取音频轨（16k 单声道 WAV），AI 只处理音频，不把整个视频丢给模型
- 🎯 **时序质量好**：默认「自动模式」优先使用实时模型（VAD 语音活动检测切句），每条字幕贴合实际说话时间
- 🌐 **语言统一**：`--lang en/zh` 在 API 层约束语种 + 输出层过滤非目标语言字幕，纯英文视频不再出现中文幻觉
- 🖥️ **双形态**：图形界面（文件选择/设置/进度/复制/导出）+ 命令行（便于脚本化调用）
- 🔒 **Key 不内嵌**：API Key 运行时读取（界面填写 / 环境变量 / 本地文件），不写死在程序里

## 📦 快速开始

### 方式一：直接下载 EXE（推荐）

1. 下载 [`dist/subtitle_gen.exe`](dist/subtitle_gen.exe)（约 85MB，内嵌 ffmpeg）
2. 双击运行 → 图形界面；或命令行调用（见下文）

### 方式二：从源码运行

```bash
# 1. 安装依赖（仅 dashscope 即可，无需 streamlit）
pip install dashscope>=1.14.0
# 2. 确保 ffmpeg 在 PATH（或用 FFMPEG_DIR 环境变量指定目录）
# 3. 运行
python src/test_local.py 视频.mp4 --lang en
```

## 🔑 API Key 配置（三选一，优先级从高到低）

1. 命令行 `--api-key sk-xxx`
2. 环境变量 `DASHSCOPE_API_KEY`
3. EXE 同目录放 `subtitle_key.txt`（首行写 Key，`#` 开头为注释）

```powershell
# 方式2
$env:DASHSCOPE_API_KEY = "sk-xxx"
subtitle_gen.exe video.mp4 --lang en

# 方式3：在 EXE 同目录创建 subtitle_key.txt，参照 subtitle_key.txt.example
```

> ⚠️ 请从 [阿里云百炼控制台](https://bailian.console.aliyun.com/) 获取你自己的 Key。**本程序不内置任何 Key。**

## 🖥️ 使用方式

### 图形界面

双击 `subtitle_gen.exe`，界面提供：文件选择、模式（自动/实时/离线）、语言、API Key、进度显示，结果支持**复制到剪贴板**和**导出 .srt**。

### 命令行

```
subtitle_gen.exe <视频/音频文件> [选项]
```

| 参数 | 说明 |
|---|---|
| （不加模式参数） | **自动模式（默认）**：优先实时，失败自动回退离线 |
| `--realtime` | 强制实时（VAD 切句，时间对齐更好） |
| `--offline` | 强制离线（超长视频） |
| `--lang en\|zh` | 语言统一输出（英文/中文） |
| `--model M` | 离线模型（默认 paraformer-v2） |
| `-o out.srt` | 输出路径（默认 `<输入名>_local.srt`） |
| `--keep-wav` | 保留提取的 16k WAV |
| `--timeout T` | 超时秒数（SDK websocket + 看门狗；默认: 实时 600 / 离线 1800） |
| `--api-key KEY` | 显式传 Key |
| `--key-file F` | 从文件读 Key |
| `--check` | 环境自检 |

示例：

```powershell
subtitle_gen.exe "视频.mp4" --lang en                      # 自动模式（推荐）
subtitle_gen.exe "视频.mp4" --realtime --lang en           # 强制实时
subtitle_gen.exe "视频.mp4" --offline --lang en -o out.srt # 超长视频强制离线
subtitle_gen.exe --check
```

### 模式与时序（为什么默认自动）

字幕的**时间对齐**取决于切句方式：

| 模式 | 切句方式 | 时序特点 |
|---|---|---|
| **实时**（paraformer-realtime-v2） | VAD 语音活动检测 | 在语音停顿处断开，每条字幕贴合实际说话时间，**对齐更好** |
| **离线**（paraformer-v2） | 句法 / 标点 | 长条合并、可能跨静音段，观感对齐较差 |

- 默认自动模式优先实时，保证时序质量；识别失败自动回退离线（超长视频保底），不会卡死。
- 实时模式的 SDK websocket 总超时已从默认 300s 提高到 **600s**，服务端较慢时的偶发超时大幅减少。

## 🔧 从源码构建 EXE

```bash
pip install pyinstaller
cd src
python -m PyInstaller subtitle_gen.spec --clean --noconfirm
# 产物: dist/subtitle_gen.exe
```

> 构建要求：Python 3.9+，已装 dashscope；ffmpeg 在 PATH 或设置 `FFMPEG_DIR` 环境变量（用于内嵌进 EXE）。

## 🔌 供其他程序调用（CLI 契约）

公网网页因浏览器沙箱**无法直接调用本地 EXE**；若你的 Node/桌面应用要调用，可用 `child_process.spawn`：

```js
const { spawn } = require('child_process');
const child = spawn('subtitle_gen.exe', [
  videoPath, '--lang', 'en', '-o', srtOut   // 默认自动模式，时序最好
], {
  env: { ...process.env, DASHSCOPE_API_KEY: userKey }  // Key 走环境变量，勿放命令行
});
child.stdout.on('data', d => console.log(d.toString()));  // 状态/进度
child.on('close', code => { /* code 0 = 成功，srtOut 即结果 */ });
```

- Key 走环境变量，避免出现在进程列表
- 结果从 `-o` 指定的 SRT 读取；退出码 `0` 成功，非 0 失败
- 仅超长视频才加 `--offline`

## ⚠️ 注意事项

- **需要联网**：识别调用 DashScope 云端 API
- **隐私**：视频只在本机提取音频，仅把 16k 音频发送到 DashScope（用你自己的 Key）
- **API 成本**：识别消耗你的 DashScope 用量
- **支持格式**：mp4 / mp3 / wav / m4a / flac / mov / avi

## 📄 许可证

[MIT License](LICENSE)
