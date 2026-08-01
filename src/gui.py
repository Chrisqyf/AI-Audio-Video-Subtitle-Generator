#!/usr/bin/env python3
"""字幕生成 GUI (Tkinter) — 独立 EXE 的交互界面。

无参数启动时由 run_cli.py 调用；也可 `python gui.py` 直接运行（开发模式）。
复用 test_local.py 的全部核心逻辑：两阶段音频提取、实时/离线 v2 模型、
language_hints + CJK 过滤器。转写在后台线程执行，界面不卡顿。
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 无论从哪个目录运行，都确保能导入同目录的 test_local / audio_processor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_local

# 仅保留已验证可用的离线模型 (paraformer-v2)。
# 已实测: qwen3-asr-flash 不兼容经典 Transcription API (url error)，
#         paraformer-16k-1 该账号无权限 (AccessDenied)。
MODELS = ['paraformer-v2']
LANG_MAP = {'不指定': '', '英文': 'en', '中文': 'zh'}
OFFLINE_TIMEOUT = 1800  # 离线转写轮询最长等待秒数


class SubtitleApp:
    def __init__(self, root):
        self.root = root
        root.title('AI 字幕生成器')
        root.geometry('760x700')
        root.minsize(640, 560)

        self._q = queue.Queue()
        self._worker = None
        self._start_time = None
        self._timer_id = None
        self._base_status = '就绪'

        self._build_ui()
        self._on_mode()

    # ---------- 界面 ----------
    def _build_ui(self):
        # 文件选择
        frm_file = ttk.LabelFrame(self.root, text='文件', padding=8)
        frm_file.pack(fill='x', padx=10, pady=6)
        self.file_var = tk.StringVar()
        ttk.Entry(frm_file, textvariable=self.file_var).pack(
            side='left', fill='x', expand=True, padx=(0, 6))
        ttk.Button(frm_file, text='选择文件…', command=self._pick_file).pack(side='left')

        # 设置
        cfg = ttk.LabelFrame(self.root, text='设置', padding=8)
        cfg.pack(fill='x', padx=10, pady=6)

        row_mode = tk.Frame(cfg)
        row_mode.pack(fill='x')
        ttk.Label(row_mode, text='模式:').pack(side='left')
        self.mode_var = tk.StringVar(value='auto')
        ttk.Radiobutton(row_mode, text='自动(推荐)', variable=self.mode_var,
                        value='auto', command=self._on_mode).pack(side='left', padx=6)
        ttk.Radiobutton(row_mode, text='实时', variable=self.mode_var,
                        value='realtime', command=self._on_mode).pack(side='left', padx=6)
        ttk.Radiobutton(row_mode, text='离线', variable=self.mode_var,
                        value='offline', command=self._on_mode).pack(side='left', padx=6)

        row_model = tk.Frame(cfg)
        row_model.pack(fill='x', pady=(6, 0))
        ttk.Label(row_model, text='离线模型:').pack(side='left')
        self.model_var = tk.StringVar(value='paraformer-v2')
        self.model_box = ttk.Combobox(row_model, textvariable=self.model_var,
                                      values=MODELS, state='readonly', width=20)
        self.model_box.pack(side='left', padx=6)
        ttk.Label(row_model, text='语言:').pack(side='left', padx=(14, 0))
        self.lang_var = tk.StringVar(value='不指定')
        ttk.Combobox(row_model, textvariable=self.lang_var, values=list(LANG_MAP),
                     state='readonly', width=8).pack(side='left', padx=6)

        row_key = tk.Frame(cfg)
        row_key.pack(fill='x', pady=(6, 0))
        ttk.Label(row_key, text='API Key:').pack(side='left')
        self.key_var = tk.StringVar()
        ttk.Entry(row_key, textvariable=self.key_var, show='*', width=42).pack(side='left', padx=6)
        self.keep_wav_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row_key, text='保留16k WAV', variable=self.keep_wav_var).pack(
            side='left', padx=(14, 0))

        # 操作与状态
        act = tk.Frame(self.root)
        act.pack(fill='x', padx=10, pady=4)
        self.start_btn = ttk.Button(act, text='开始生成', command=self._start)
        self.start_btn.pack(side='left')
        self.status_var = tk.StringVar(value='就绪')
        ttk.Label(act, textvariable=self.status_var).pack(side='left', padx=12)

        # 结果区
        res = ttk.LabelFrame(self.root, text='结果 (SRT)', padding=8)
        res.pack(fill='both', expand=True, padx=10, pady=6)
        text_wrap = tk.Frame(res)
        text_wrap.pack(fill='both', expand=True)
        self.text = tk.Text(text_wrap, wrap='none', font=('Consolas', 10))
        scroll = ttk.Scrollbar(text_wrap, orient='vertical', command=self.text.yview)
        self.text.config(yscrollcommand=scroll.set)
        self.text.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')

        btns = tk.Frame(res)
        btns.pack(fill='x', pady=(6, 0))
        ttk.Button(btns, text='复制', command=self._copy).pack(side='left')
        ttk.Button(btns, text='导出 .srt', command=self._export).pack(side='left', padx=6)
        ttk.Button(btns, text='清空', command=self._clear).pack(side='left', padx=6)

    def _on_mode(self):
        """仅离线模式需要离线模型下拉框。"""
        if self.mode_var.get() == 'offline':
            self.model_box.config(state='readonly')
        else:
            self.model_box.config(state='disabled')

    # ---------- 操作 ----------
    def _pick_file(self):
        path = filedialog.askopenfilename(
            title='选择音视频文件',
            filetypes=[('音视频', '*.mp4 *.mp3 *.wav *.m4a *.flac *.mov *.avi'),
                       ('所有文件', '*.*')])
        if path:
            self.file_var.set(path)

    def _start(self):
        if self._worker and self._worker.is_alive():
            return
        audio = self.file_var.get().strip()
        if not audio:
            messagebox.showwarning('提示', '请先选择音视频文件')
            return
        if not os.path.isfile(audio):
            messagebox.showerror('错误', f'文件不存在: {audio}')
            return
        key = self.key_var.get().strip() or test_local.resolve_api_key(None)
        if not key:
            messagebox.showerror(
                '错误',
                '未提供 API Key。\n请在“设置”中填写，或设置环境变量 DASHSCOPE_API_KEY，'
                '或在 EXE 同目录放 subtitle_key.txt。')
            return

        self.start_btn.config(state='disabled')
        self._base_status = '正在提取音频...'
        self.status_var.set(self._base_status)
        self.text.delete('1.0', 'end')
        self._start_time = time.time()
        self._timer_id = self.root.after(1000, self._tick)

        self._worker = threading.Thread(
            target=self._work,
            args=(audio, key, self.mode_var.get(), self.model_var.get(),
                  LANG_MAP.get(self.lang_var.get(), ''), self.keep_wav_var.get()),
            daemon=True)
        self._worker.start()

    def _tick(self):
        """每秒轮询: 更新耗时 + 处理后台线程消息。"""
        done = False
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == 'status':
                    self._base_status = payload
                    self.status_var.set(payload)
                elif kind == 'done':
                    srt, cue_count = payload
                    self.text.delete('1.0', 'end')
                    self.text.insert('1.0', srt)
                    self._base_status = f'完成: {cue_count} 条字幕'
                    self.status_var.set(self._base_status)
                    done = True
                elif kind == 'error':
                    messagebox.showerror('生成失败', payload)
                    self._base_status = '失败'
                    self.status_var.set(self._base_status)
                    done = True
        except queue.Empty:
            pass

        if done:
            self._stop_timer()
            self.start_btn.config(state='normal')
            return
        if self._start_time:
            self.status_var.set(f'{self._base_status}   (已运行 {int(time.time() - self._start_time)} 秒)')
            self._timer_id = self.root.after(1000, self._tick)

    def _work(self, audio, key, mode, model, lang, keep_wav):
        temp_wav = os.path.splitext(audio)[0] + "_16k.wav"
        try:
            self._q.put(('status', '阶段1: 提取音频...'))
            test_local.extract_audio(audio, temp_wav)
            if mode == 'offline':
                self._q.put(('status', '阶段2: 离线转写中...'))
                srt = test_local.transcribe_offline(
                    temp_wav, key, model, lang, OFFLINE_TIMEOUT,
                    progress_cb=lambda m: self._q.put(('status', m)))
            elif mode == 'realtime':
                self._q.put(('status', '阶段2: 实时识别中...'))
                srt = test_local.transcribe_realtime(
                    temp_wav, key, lang,
                    progress_cb=lambda m: self._q.put(('status', m)))
            else:  # auto: 优先实时，失败回退离线
                self._q.put(('status', '阶段2: 自动模式 — 优先实时，失败回退离线...'))
                srt = test_local.transcribe_auto(
                    temp_wav, key, model, lang, OFFLINE_TIMEOUT,
                    progress_cb=lambda m: self._q.put(('status', m)))
            if lang:
                srt, removed = test_local.filter_srt_by_language(srt, lang)
                if removed:
                    self._q.put(('status', f'语言过滤: 移除 {removed} 条非目标语言'))
            elif test_local._CJK_RE.search(srt or ""):
                self._q.put(('status', '提示: 结果含中文字幕，可在设置中选“英文”统一输出'))
            cue_count = sum(1 for line in srt.splitlines() if '-->' in line)
            self._q.put(('done', (srt, cue_count)))
        except Exception as e:
            self._q.put(('error', str(e)))
        finally:
            if not keep_wav and os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass

    def _copy(self):
        srt = self.text.get('1.0', 'end-1c').strip()
        if srt:
            self.root.clipboard_clear()
            self.root.clipboard_append(srt)
            self.root.update()
            self._base_status = '已复制到剪贴板'
            self.status_var.set(self._base_status)

    def _export(self):
        srt = self.text.get('1.0', 'end-1c').strip()
        if not srt:
            messagebox.showwarning('提示', '没有可导出的结果')
            return
        base = os.path.splitext(os.path.basename(self.file_var.get() or 'subtitles'))[0]
        path = filedialog.asksaveasfilename(
            defaultextension='.srt', initialfile=base + '.srt',
            filetypes=[('SRT 字幕', '*.srt')])
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(srt + '\n')
            self._base_status = f'已导出: {os.path.basename(path)}'
            self.status_var.set(self._base_status)

    def _clear(self):
        self.text.delete('1.0', 'end')
        self._base_status = '就绪'
        self.status_var.set(self._base_status)

    def _stop_timer(self):
        if self._timer_id:
            try:
                self.root.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None
        self._start_time = None

    def on_close(self):
        self._stop_timer()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = SubtitleApp(root)
    root.protocol('WM_DELETE_WINDOW', app.on_close)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
