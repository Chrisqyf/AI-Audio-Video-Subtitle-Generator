#!/usr/bin/env python3
"""
web_app 本地测试脚本
====================
直接复用 web_app 的核心处理模块 audio_processor.generate_srt，
与 Streamlit 前端 (app.py) 调用的是【同一个函数】，保证业务逻辑 100% 一致。
仅依赖 dashscope（无需 streamlit），可在本地命令行完整跑通字幕生成流程。

用法:
    python test_local.py --check                                  # 环境自检（无需 API Key）
    python test_local.py <音频/视频文件> [--api-key KEY] [-o out.srt]   # 默认自动: 实时优先, 失败回退离线
    python test_local.py <音频/视频文件> --realtime               # 强制实时 (VAD 切句, 时间对齐更好)
    python test_local.py <音频/视频文件> --offline                # 强制离线 (很长视频)
    python test_local.py <音频/视频文件> --lang en                # 语言统一: 只保留英文 + API language_hints
    python test_local.py --print-only <文件> [--api-key KEY]      # 只打印不落盘

API Key 来源优先级:
    1. --api-key 参数
    2. 环境变量 DASHSCOPE_API_KEY
    3. --key-file 指定的文件 / EXE(脚本)同目录的 subtitle_key.txt
    4. 本文件顶部的 DEFAULT_API_KEY 常量 (仅开发模式；EXE 构建时会清空此值)

两阶段流程 (音频优先):
    阶段1: ffmpeg -vn 从视频自动提取音频轨，转为 16k 单声道 WAV，并验证时长/大小。
    阶段2: AI (实时或离线) 只处理阶段1提取出的 WAV，绝不把整个视频丢给 AI。
    提取失败会直接报错，不会静默回退到原视频文件。--keep-wav 可保留提取的音频。

语言统一输出 (--lang):
    - 实时模型已升级为 paraformer-realtime-v2，离线默认 paraformer-v2。
      v2 模型支持 language_hints，--lang en/zh 时 API 层即约束语种，减少跨语言误识别。
    - 输出层再叠加过滤器：--lang en 移除含中日韩字符的字幕，100% 保证英文统一。

关于实时 vs 离线 (重要):
    - 默认自动模式: 优先实时 (paraformer-realtime-v2, VAD 切句时间对齐更好)，
      失败自动回退离线 (paraformer-v2)。
    - --realtime 强制实时 (中短音频)；--offline 强制离线 (很长视频)。
    - 离线: 提取音频 -> 上传 Files.get 签名URL -> Transcription 异步任务
      (默认 paraformer-v2，仅此模型验证可用)，适合超长文件。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time

# CJK 字符范围 (中日韩统一表意文字 + 扩展A + 假名 + 谚文 + 兼容表意文字)
_CJK_RE = re.compile(r'[㐀-䶿一-鿿぀-ヿ가-힯豈-﫿]')

# 无论从哪个目录运行，都确保能导入同目录下的 audio_processor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows 控制台默认 GBK 编码，统一改为 UTF-8 输出，避免中文乱码
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 修复 dashscope SDK 在 Windows 退出时的 "Event loop is closed" 警告:
# dashscope.common.utils.iter_over_async 用 new_event_loop() 创建事件循环后从不关闭，
# Windows 默认 Proactor 循环的 pipe transport 在解释器退出时才被回收，
# __del__ 时循环已关闭 -> 抛 RuntimeError。切换为 Selector 策略后，
# transport 的 __del__ 只关闭 socket，不再触发该错误 (aiohttp websocket 完全兼容)。
if sys.platform == 'win32':
    try:
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# 懒加载：audio_processor 顶层会 import dashscope，
# 未安装时让 --check 模式仍能优雅报告，而不是直接崩溃
try:
    from audio_processor import generate_srt, format_time_srt
    IMPORT_OK = True
    IMPORT_ERROR = None
except ImportError as _e:
    IMPORT_OK = False
    IMPORT_ERROR = _e

# 与 app.py 中 file_uploader 的 type 列表保持一致
SUPPORTED_EXTS = {'.mp4', '.mp3', '.wav', '.m4a', '.flac', '.mov', '.avi'}

# 备用 API Key。⚠️ 公开部署时请保持为空，Key 一律运行时读取
# (环境变量 DASHSCOPE_API_KEY / --api-key / subtitle_key.txt)，避免泄露。
DEFAULT_API_KEY = ''


def check_environment():
    """环境自检：依赖、ffmpeg、纯逻辑函数。不调用任何 API。"""
    print("===== web_app 本地测试 - 环境自检 =====\n")
    ok = True

    # 1. dashscope / audio_processor 可导入性
    if IMPORT_OK:
        import dashscope
        print(f"[OK] dashscope 已安装 (版本: {getattr(dashscope, '__version__', '未知')})")
    else:
        print(f"[FAIL] dashscope 未安装，无法导入 audio_processor。请运行:  pip install -r requirements.txt")
        ok = False

    # 2. ffmpeg (核心逻辑中转换 16k WAV 必需)
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        print(f"[OK] ffmpeg 已找到: {ffmpeg}")
    else:
        print("[FAIL] ffmpeg 未找到，请安装并加入 PATH（转换 16k WAV 时必需）")
        ok = False

    # 3. 纯逻辑函数自检 (无需 API，需 dashscope 可导入)
    print("\n---- format_time_srt 纯逻辑自检 ----")
    if IMPORT_OK:
        cases = [
            (0,        "00:00:00,000"),
            (1000,     "00:00:01,000"),
            (59999,    "00:00:59,999"),
            (61234,    "00:01:01,234"),
            (3661000,  "01:01:01,000"),
        ]
        for ms, expect in cases:
            got = format_time_srt(ms)
            status = "OK" if got == expect else f"FAIL (期望 {expect})"
            if got != expect:
                ok = False
            print(f"  format_time_srt({ms}) = {got}  [{status}]")
    else:
        print(f"  跳过 (导入失败: {IMPORT_ERROR})")

    print()
    print("结论:", "环境正常，可进行完整测试。" if ok else "存在问题，请按上方提示修复后重试。")
    return 0 if ok else 1


def _auto_key_file():
    """自动探测的 Key 文件：EXE 或脚本同目录的 subtitle_key.txt"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'subtitle_key.txt')


def _read_key_file(path):
    """读取 Key 文件首行非空、非 # 注释的内容。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    return line
    except Exception:
        pass
    return None


def resolve_api_key(arg_key, key_file=None):
    """解析 API Key，优先级:
    --api-key 参数 > 环境变量 DASHSCOPE_API_KEY > --key-file > 自动 subtitle_key.txt
    > DEFAULT_API_KEY 常量 (仅开发模式，EXE 内已清空)"""
    if arg_key:
        return arg_key
    env = os.environ.get('DASHSCOPE_API_KEY')
    if env:
        return env
    for path in ([key_file] if key_file else []) + [_auto_key_file()]:
        k = _read_key_file(path)
        if k:
            return k
    if DEFAULT_API_KEY:
        return DEFAULT_API_KEY
    return None


class _Watchdog(threading.Thread):
    """后台看门狗：定期打印已运行耗时；超过硬性超时后强制终止 (os._exit)。

    背景: paraformer-realtime-v1 是实时流式模型，对中长视频按接近实时的速度处理，
    且 dashscope SDK 内部 websocket 有 300 秒总超时。为避免静默挂起，
    看门狗让运行状态可见，并在超时后以清晰报错退出。
    """

    def __init__(self, hard_deadline, report_interval=15, timeout_hint=""):
        super().__init__(daemon=True)
        self._deadline = hard_deadline
        self._interval = report_interval
        self._hint = timeout_hint
        self._start = time.time()
        self._last_report = self._start

    def run(self):
        while True:
            time.sleep(1)
            now = time.time()
            elapsed = now - self._start
            if now - self._last_report >= self._interval:
                self._last_report = now
                print(f"[看门狗] 已运行 {elapsed:.0f} 秒... (硬性超时 {self._deadline:.0f} 秒)",
                      flush=True)
            if elapsed >= self._deadline:
                print(f"[看门狗] ⏰ 超过 {self._deadline:.0f} 秒仍未完成，强制终止。{self._hint}",
                      flush=True)
                os._exit(1)


def _wav_duration(wav_path):
    """获取 WAV 时长（秒）。优先 ffprobe，失败则解析 WAV 头。"""
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', wav_path],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return float(out.stdout.strip())
    except Exception:
        pass
    try:
        with open(wav_path, 'rb') as f:
            data = f.read()
        if data[0:4] == b'RIFF' and data[8:12] == b'WAVE':
            i = 12
            while i < len(data) - 8:
                cid = data[i:i + 4]
                size = int.from_bytes(data[i + 4:i + 8], 'little')
                if cid == b'data':
                    # 16kHz 单声道 16bit => 32000 字节/秒
                    return size / 32000.0
                i += 8 + size + (size % 2)
    except Exception:
        pass
    return None


def extract_audio(input_path, output_wav):
    """阶段1: 从视频中自动提取音频轨，转为 16k 单声道 WAV。

    使用 -vn 显式丢弃视频流，确保后续 AI 只处理音频。
    提取失败时直接报错，不静默回退到原视频文件 (避免 AI 拿到整个视频)。
    """
    cmd = ['ffmpeg', '-y', '-i', input_path, '-vn', '-ar', '16000', '-ac', '1', output_wav]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode != 0 or not os.path.exists(output_wav) or os.path.getsize(output_wav) == 0:
        raise Exception(
            f"ffmpeg 音频提取失败 (exit={result.returncode})。请确认 {input_path} 包含可解码的音频轨。"
        )
    dur = _wav_duration(output_wav)
    size_mb = os.path.getsize(output_wav) / 1024 / 1024
    print(f"    ✅ 音频已提取: {os.path.basename(output_wav)} "
          f"({size_mb:.2f} MB" + (f", 时长 {dur / 60:.1f} 分钟" if dur else "") + ")", flush=True)
    return output_wav


def _dict_get(obj, key):
    """兼容 dict / 对象两种响应结构取值。"""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _upload_to_dashscope(file_path, api_key):
    """上传本地文件并返回可访问的【签名 HTTP URL】(离线转写 file_urls 需要)。

    流程: Files.upload -> Files.get(file_id) -> output.url
    说明: 不能用 file://file_id 或 oss:// 引用 —— paraformer-v2 云端 worker
    无法从这两种引用下载文件 (实测 DECODE_ERROR / SERVER_ERROR / FILE_DOWNLOAD_FAILED)。
    """
    import dashscope
    dashscope.api_key = api_key
    print(f"    上传文件: {os.path.basename(file_path)} "
          f"({os.path.getsize(file_path) / 1024 / 1024:.2f} MB)...")
    up = dashscope.Files.upload(file_path, purpose='file-extract')
    if up.status_code != 200:
        raise Exception(f"文件上传失败: {up.code} - {up.message}")
    uploaded = _dict_get(up.output, 'uploaded_files')
    file_id = _dict_get(uploaded[0], 'file_id') if uploaded else None
    if not file_id:
        raise Exception(f"上传响应缺少 file_id: {up.output}")
    info = dashscope.Files.get(file_id)
    if info.status_code != 200:
        raise Exception(f"获取文件 URL 失败: {info.code} - {info.message}")
    url = _dict_get(info.output, 'url')
    if not url:
        raise Exception(f"Files.get 响应缺少 url: {info.output}")
    return url


def _fetch_offline_result(wait_response):
    """从 Transcription.wait 的 SUCCEEDED 响应中解析句子并生成 SRT 字符串。

    paraformer-v2 结果结构: results[0].transcription_url 指向 JSON,
    JSON 内 transcripts[].sentences[] 每条含 begin_time/end_time/text。
    """
    import requests
    results = _dict_get(wait_response.output, 'results') or []
    if not results:
        raise Exception("转写成功但响应缺少 results")
    r0 = results[0]
    turl = (_dict_get(r0, 'transcription_url')
            or _dict_get(_dict_get(r0, 'output') or {}, 'transcription_url'))
    if not turl:
        raise Exception(f"结果缺少 transcription_url: {r0}")
    data = requests.get(turl, timeout=120).json()
    sentences = []
    if isinstance(data, dict):
        for t in data.get('transcripts') or []:
            sentences.extend(t.get('sentences') or [])
    if not sentences:
        raise Exception("转写结果中没有句子 (音频可能没有清晰人声)")
    srt_lines = []
    for i, sent in enumerate(sentences):
        begin = _dict_get(sent, 'begin_time')
        end = _dict_get(sent, 'end_time')
        text = _dict_get(sent, 'text')
        if begin is not None and end is not None and text:
            srt_lines.append(
                f"{i + 1}\n{format_time_srt(begin)} --> {format_time_srt(end)}\n{text}\n"
            )
    if not srt_lines:
        raise Exception("未识别到有效句子")
    return "\n".join(srt_lines)


def transcribe_realtime(wav_path, api_key, lang, progress_cb=None, request_timeout=600):
    """核心函数: 实时模型转写，返回 SRT 字符串（不写文件）。

    Args:
        wav_path: 已提取的 16k WAV 路径
        api_key: DashScope API Key
        lang: 'en'/'zh'/None
        progress_cb: 可选回调，接收状态文本 (GUI 用它刷新进度)
        request_timeout: websocket 总超时秒数，默认 600 (覆盖 SDK 300s 默认)，
            避免服务端较慢时实时识别中途超时中断
    """
    if not IMPORT_OK:
        raise Exception(f"无法导入 audio_processor: {IMPORT_ERROR}")
    if progress_cb:
        progress_cb("正在实时识别 (paraformer-realtime-v2)...")
    hints = _lang_hints(lang)
    return generate_srt(wav_path, api_key, already_wav=True, language_hints=hints,
                        request_timeout=request_timeout)


def transcribe_offline(wav_path, api_key, model, lang, timeout, progress_cb=None):
    """核心函数: 离线转写，返回 SRT 字符串（不写文件）。

    Args:
        wav_path: 已提取的 16k WAV 路径
        api_key: DashScope API Key
        model: 离线模型 (paraformer-v2 / qwen3-asr-flash / sensevoice-v1)
        lang: 'en'/'zh'/None
        timeout: 轮询最长等待秒数
        progress_cb: 可选回调，接收状态文本
    """
    def _cb(msg):
        if progress_cb:
            progress_cb(msg)

    from dashscope.audio.asr import Transcription
    file_url = _upload_to_dashscope(wav_path, api_key)
    _cb(f"上传完成")

    hints = _lang_hints(lang)
    async_kwargs = {}
    if hints:
        async_kwargs['language_hints'] = hints
    task_response = Transcription.async_call(model=model, file_urls=[file_url], **async_kwargs)
    if task_response.status_code != 200:
        raise Exception(f"任务提交失败: {task_response.code} - {task_response.message}")
    task_id = task_response.output.task_id
    _cb(f"任务已提交: {task_id}")

    deadline = time.time() + timeout
    while True:
        if time.time() >= deadline:
            raise Exception(f"转写超时 ({timeout} 秒)，任务 id: {task_id}")
        wait_response = Transcription.wait(task=task_id)
        status = wait_response.output.task_status
        if status == 'SUCCEEDED':
            _cb("转写完成，下载结果...")
            return _fetch_offline_result(wait_response)
        elif status == 'FAILED':
            msg = (_dict_get(wait_response.output, 'message')
                   or _dict_get(wait_response.output, 'code') or '未知错误')
            raise Exception(f"转写失败: {msg}")
        else:
            print(f"    状态: {status}...", flush=True)
            _cb(f"状态: {status}...")
            time.sleep(2)


def transcribe_auto(wav_path, api_key, model, lang, timeout, progress_cb=None):
    """自动模式: 优先实时(时间对齐好)，失败自动回退离线(长视频保底)。

    说明: 实时模型按 VAD 切句，字幕对齐更贴合语音；离线按句法切句，
    长条字幕可能跨静音。对中短音频实时更优，失败时回退离线保证可用。
    """
    def _cb(msg):
        if progress_cb:
            progress_cb(msg)

    _cb("自动模式: 优先实时识别 (paraformer-realtime-v2)...")
    try:
        # 实时尝试给足 600s 预算，覆盖服务端较慢的情况
        return transcribe_realtime(wav_path, api_key, lang, progress_cb, request_timeout=600)
    except Exception as e:
        _cb(f"实时识别失败 ({str(e)[:50]})，自动切换离线转写...")
        return transcribe_offline(wav_path, api_key, model, lang, timeout, progress_cb)


def run_offline(audio_path, api_key, model, output_path, print_only, timeout, keep_wav, lang):
    """长视频离线转写：阶段1 ffmpeg 提取音频 -> 阶段2 上传 + 异步转写 -> 轮询 -> SRT。

    与 web_app 的核心链路保持一致的音频提取 (ffmpeg -> 16k WAV)，
    但 AI 识别改用离线批量模型，适合 5 分钟以上的长视频。
    """
    if not IMPORT_OK:
        print(f"错误: 无法导入 audio_processor: {IMPORT_ERROR}")
        print("请先安装依赖:  pip install -r requirements.txt")
        return 1
    if not os.path.isfile(audio_path):
        print(f"错误: 文件不存在 - {audio_path}")
        return 1

    temp_wav = os.path.splitext(audio_path)[0] + "_16k.wav"
    try:
        print(f"[1/3] 阶段1: 自动提取音频 (ffmpeg -vn 转 16k mono WAV)...")
        extract_audio(audio_path, temp_wav)
        print(f"      阶段2: 上传提取出的音频并离线转写 — AI 只处理该音频")
        hints = _lang_hints(lang)
        hint_msg = f", language_hints={hints}" if hints else ""
        print(f"[2/3] 提交离线转写任务 (model={model}{hint_msg})...")
        srt_result = transcribe_offline(temp_wav, api_key, model, lang, timeout)
        return _emit_srt(srt_result, output_path, print_only, audio_path, lang)
    except Exception as e:
        print(f"❌ 离线转写失败: {e}")
        return 1
    finally:
        if not keep_wav and os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass


def run_auto(audio_path, api_key, model, output_path, print_only, timeout, keep_wav, lang):
    """自动模式: 阶段1 提取音频，阶段2 优先实时(对齐好)失败回退离线(长视频保底)。"""
    if not IMPORT_OK:
        print(f"错误: 无法导入 audio_processor: {IMPORT_ERROR}")
        print("请先安装依赖:  pip install -r requirements.txt")
        return 1
    if not os.path.isfile(audio_path):
        print(f"错误: 文件不存在 - {audio_path}")
        return 1
    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        print(f"警告: 扩展名 '{ext}' 不在 web 端支持列表 {sorted(SUPPORTED_EXTS)} 中，仍将尝试处理。")

    temp_wav = os.path.splitext(audio_path)[0] + "_16k.wav"
    print(f"[1/3] 输入文件: {audio_path} ({os.path.getsize(audio_path) / 1024 / 1024:.2f} MB)")
    print("[2/3] 阶段1: 自动提取音频 (ffmpeg -vn 转 16k mono WAV)...")
    try:
        extract_audio(audio_path, temp_wav)
        print(f"      阶段2: 自动模式 — 优先实时识别(时间对齐好)，失败自动回退离线")
        srt_result = transcribe_auto(temp_wav, api_key, model, lang, timeout)
    except Exception as e:
        print(f"[3/3] ❌ 生成失败: {e}")
        print("常见排查: 1. API Key 是否有效?  2. 音频是否包含清晰人声?  3. 文件格式是否受损?  4. ffmpeg 是否可用?")
        return 1
    finally:
        if not keep_wav and os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass

    print("[3/3]", end=" ")
    return _emit_srt(srt_result, output_path, print_only, audio_path, lang)


def filter_srt_by_language(srt_result, lang):
    """按目标语言过滤 SRT 字幕块，返回 (过滤后的srt, 移除条数)。

    lang='en': 移除包含 CJK 字符的条 (纯英文视频中偶尔出现的非英文幻觉字幕)。
    lang='zh': 移除不含 CJK 字符的条 (纯中文视频中偶尔出现的非中文幻觉字幕)。
    """
    if not lang or not srt_result.strip():
        return srt_result, 0
    blocks = re.split(r'\n\s*\n', srt_result.strip())
    kept = []
    removed = 0
    for block in blocks:
        lines = block.split('\n')
        if len(lines) < 3:
            kept.append(block)
            continue
        text = '\n'.join(lines[2:])
        has_cjk = bool(_CJK_RE.search(text))
        if (lang == 'en' and has_cjk) or (lang == 'zh' and not has_cjk):
            removed += 1
            continue
        kept.append(block)
    # 重新编号
    out = []
    for i, block in enumerate(kept, 1):
        lines = block.split('\n')
        lines[0] = str(i)
        out.append('\n'.join(lines))
    return '\n\n'.join(out), removed


def _emit_srt(srt_result, output_path, print_only, audio_path=None, lang=None):
    """按目标语言过滤、校验 SRT 结构并输出（打印 / 写文件 / 预览）。返回 0 成功，1 失败。"""
    # 语言统一过滤 (guarantee)
    if lang:
        srt_result, removed = filter_srt_by_language(srt_result, lang)
        if removed:
            print(f"    🗑️ 语言过滤 ({lang}): 移除 {removed} 条非目标语言字幕")
    elif _CJK_RE.search(srt_result or ""):
        print("    💡 提示: 检测到中文字幕。若视频为纯英文，可加 --lang en 统一为英文输出")

    cue_count = sum(1 for line in srt_result.splitlines() if '-->' in line)
    if not srt_result.strip():
        print("⚠️ 结果为空字符串")
        return 1
    if cue_count == 0:
        print("⚠️ 结果缺少时间轴 (--> 行)，SRT 结构可能异常")
        return 1
    print(f"    ✅ 生成成功: {cue_count} 条字幕")

    if print_only:
        print("\n----- SRT 内容 -----")
        print(srt_result)
    else:
        out = output_path or (os.path.splitext(audio_path or "out")[0] + "_local.srt")
        with open(out, 'w', encoding='utf-8') as f:
            f.write(srt_result)
        print(f"\n✅ SRT 已写入: {os.path.abspath(out)}")

    print("\n----- 预览 (前 500 字符) -----")
    print(srt_result[:500] + ("..." if len(srt_result) > 500 else ""))
    return 0


def _lang_hints(lang):
    """把 --lang 转换为 API 的 language_hints 参数。"""
    if lang == "en":
        return ["en"]
    if lang == "zh":
        return ["zh"]
    return None


def run_generate(audio_path, api_key, output_path, print_only, timeout, keep_wav, lang):
    """完整流程 (实时模型 paraformer-realtime-v2)：
    阶段1 用 ffmpeg 从视频提取音频 (16k mono WAV)，阶段2 让 AI 只处理该音频。"""
    if not IMPORT_OK:
        print(f"错误: 无法导入 audio_processor: {IMPORT_ERROR}")
        print("请先安装依赖:  pip install -r requirements.txt")
        return 1
    if not os.path.isfile(audio_path):
        print(f"错误: 文件不存在 - {audio_path}")
        return 1

    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in SUPPORTED_EXTS:
        print(f"警告: 扩展名 '{ext}' 不在 web 端支持列表 {sorted(SUPPORTED_EXTS)} 中，仍将尝试处理。")

    temp_wav = os.path.splitext(audio_path)[0] + "_16k.wav"
    print(f"[1/3] 输入文件: {audio_path} ({os.path.getsize(audio_path) / 1024 / 1024:.2f} MB)")
    print("[2/3] 阶段1: 自动提取音频 (ffmpeg -vn 转 16k mono WAV)...")
    try:
        extract_audio(audio_path, temp_wav)
        hints = _lang_hints(lang)
        hint_msg = f", language_hints={hints}" if hints else ""
        print(f"      阶段2: 调用 transcribe_realtime() — AI 只处理提取出的音频 "
              f"(模型 paraformer-realtime-v2{hint_msg})")
        print(f"      ⚠️ 实时模型对长视频处理很慢且 SDK 内部 300s 超时；5 分钟以上请改用 --offline")
        watchdog = _Watchdog(
            hard_deadline=timeout,
            timeout_hint="长视频请改用 --offline 离线转写模式。",
        )
        watchdog.start()
        # SDK 超时与看门狗对齐到 timeout，避免服务端较慢时实时识别超时
        srt_result = transcribe_realtime(temp_wav, api_key, lang, request_timeout=timeout)
    except Exception as e:
        print(f"[3/3] ❌ 生成失败: {e}")
        print("常见排查: 1. API Key 是否有效?  2. 音频是否包含清晰人声?  3. 文件格式是否受损?  4. ffmpeg 是否可用?")
        print("         若为超时/处理过慢，5 分钟以上音视频请改用 --offline 离线转写模式。")
        return 1
    finally:
        if not keep_wav and os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass

    print("[3/3]", end=" ")
    return _emit_srt(srt_result, output_path, print_only, audio_path, lang)


def main():
    parser = argparse.ArgumentParser(
        description="web_app 本地测试：复用 audio_processor.generate_srt，与 web 端逻辑一致",
        epilog="示例:\n"
               "  python test_local.py --check\n"
               "  python test_local.py my_video.mp4                      # 实时模型 (web_app 同款逻辑)\n"
               "  python test_local.py my_video.mp4 --offline            # 长视频离线转写 (推荐 5 分钟以上)\n"
               "  python test_local.py my_video.mp4 --offline --model paraformer-v1\n"
               "  python test_local.py my_video.mp4 --timeout 600        # 自定义硬性超时",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('audio', nargs='?', help='音频/视频文件路径')
    parser.add_argument('--api-key', help='DashScope API Key (优先于环境变量 DASHSCOPE_API_KEY)')
    parser.add_argument('-o', '--output', help='输出 SRT 路径 (默认: <输入名>_local.srt)')
    parser.add_argument('--print-only', action='store_true', help='只打印 SRT 内容，不写入文件')
    parser.add_argument('--check', action='store_true', help='仅环境自检，不调用 API')
    parser.add_argument('--offline', action='store_true',
                        help='强制离线转写 (上传 + 异步任务)，适合很长视频')
    parser.add_argument('--realtime', action='store_true',
                        help='强制实时转写 (VAD 切句，时间对齐更好)')
    parser.add_argument('--model', default='paraformer-v2',
                        help='离线回退模型 (默认 paraformer-v2；已实测 qwen3-asr-flash 不兼容此 API，'
                             'paraformer-16k-1 需账号权限)')
    parser.add_argument('--timeout', type=float, default=None,
                        help='硬性超时/websocket 超时秒数 (默认: 实时 600 / 离线 1800)')
    parser.add_argument('--keep-wav', action='store_true',
                        help='保留提取出的 16k WAV 音频文件 (默认处理完自动删除)')
    parser.add_argument('--lang', choices=['en', 'zh'], default=None,
                        help='语言统一输出: en=只保留英文(过滤含中日韩字符的幻觉字幕)，'
                             'zh=只保留中文；同时向 API 传递 language_hints')
    parser.add_argument('--key-file', help='从指定文件读取 API Key (优先级高于环境变量低于 --api-key)')
    args = parser.parse_args()

    # 环境自检模式
    if args.check:
        sys.exit(check_environment())

    # 需要音频文件
    if not args.audio:
        parser.print_help()
        sys.exit(1)

    # 解析 API Key
    api_key = resolve_api_key(args.api_key, args.key_file)
    if not api_key:
        print("错误: 未提供 API Key。请通过 --api-key 传入、设置环境变量 DASHSCOPE_API_KEY、"
              "或用 --key-file / EXE 同目录 subtitle_key.txt 提供。")
        sys.exit(1)

    # 模式: 默认自动(实时优先、失败回退离线)；--realtime / --offline 强制指定
    if args.offline:
        mode = 'offline'
    elif args.realtime:
        mode = 'realtime'
    else:
        mode = 'auto'
    timeout = args.timeout or (600 if mode == 'realtime' else 1800)
    if mode == 'offline':
        sys.exit(run_offline(args.audio, api_key, args.model, args.output, args.print_only,
                              timeout, args.keep_wav, args.lang))
    elif mode == 'realtime':
        sys.exit(run_generate(args.audio, api_key, args.output, args.print_only,
                              timeout, args.keep_wav, args.lang))
    else:
        sys.exit(run_auto(args.audio, api_key, args.model, args.output, args.print_only,
                          timeout, args.keep_wav, args.lang))


if __name__ == '__main__':
    main()
