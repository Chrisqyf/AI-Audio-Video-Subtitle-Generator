import os
import subprocess
import dashscope
from dashscope.audio.asr import Recognition

def format_time_srt(ms_time):
    """
    将毫秒时间戳转换为 SRT 格式 (00:00:00,000)
    """
    seconds = ms_time / 1000
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(ms_time % 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

def generate_srt(audio_file_path, api_key, already_wav=False, language_hints=None, request_timeout=None):
    """
    处理音频文件并返回 SRT 格式的字符串。

    Args:
        audio_file_path (str): 本地音频/视频文件的路径
        api_key (str): DashScope API Key
        already_wav (bool): 传入的已是 16k 单声道 WAV（跳过 ffmpeg 转换）。
            web_app 调用时不传此参数，行为与之前完全一致。
        language_hints (list[str]): 语言约束，如 ["en"] 可显著减少跨语言误识别
            (仅 v2 模型支持)。
        request_timeout (int): websocket 总超时秒数。默认 None 用 SDK 的 300s；
            长音频/服务端较慢时建议提高 (如 600)，否则会因超过 300s 总超时而中断。

    Returns:
        str: 生成的 SRT 字幕内容

    Raises:
        Exception: 处理过程中的错误
    """
    # 设置 API Key
    dashscope.api_key = api_key

    temp_wav = None
    audio_source = audio_file_path

    try:
        # 1. 格式转换检查
        # 为了兼容性和流式识别的最佳效果，转换为 16k 采样率的 WAV
        # Streamlit Cloud 环境如果安装了 ffmpeg，这里可以正常工作
        temp_wav = headers = os.path.splitext(audio_file_path)[0] + "_temp_16k.wav"

        # 简单判断，如果不是wav或者为了保险起见，都进行转换
        # 传入已提取好的 16k WAV 时 (already_wav=True) 跳过转换，避免重复转换
        need_convert = not already_wav
        
        if need_convert:
            print("Converting audio to 16k WAV format...")
            try:
                # 使用 ffmpeg 转换: -ar 16000 (16k Hz), -ac 1 (Mono channel)
                subprocess.run(['ffmpeg', '-i', audio_file_path, '-ar', '16000', '-ac', '1', '-y', temp_wav], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                audio_source = temp_wav
            except Exception as e:
                # 如果 ffmpeg 失败，尝试直接使用原文件（如果是支持的格式可能成功，否则会失败）
                print(f"FFmpeg conversion failed: {e}. Trying original file.")
                audio_source = audio_file_path

        # 2. 调用 DashScope Recognition 服务
        # 使用 paraformer-realtime-v2 模型，支持长音频流式识别，不需要上传文件到 OSS，
        # 且 v2 支持 language_hints 语言约束，可显著减少跨语言误识别
        rec = Recognition(model='paraformer-realtime-v2', format='wav', sample_rate=16000, callback=None)

        print(f"Calling Recognition API for {audio_source}...")
        call_kwargs = {}
        if language_hints:
            call_kwargs['language_hints'] = language_hints
        if request_timeout:
            # 覆盖 SDK 默认 300s websocket 总超时，避免服务端较慢时实时识别中断
            call_kwargs['request_timeout'] = request_timeout
        res = rec.call(audio_source, **call_kwargs)
        
        if res.status_code == 200:
            sentences = res.output.get('sentence', [])
            if not sentences:
                sentences = res.output.get('sentences', [])
            
            if not sentences:
                raise Exception("未识别到有效的语音内容。请检查音频是否包含清晰的人声。")
            
            # 3. 构建 SRT 内容
            srt_content = []
            for i, sent in enumerate(sentences):
                begin = sent.get('begin_time')
                end = sent.get('end_time')
                text = sent.get('text')
                
                # 简单的格式校验
                if begin is not None and end is not None and text:
                    idx = i + 1
                    time_line = f"{format_time_srt(begin)} --> {format_time_srt(end)}"
                    srt_content.append(f"{idx}\n{time_line}\n{text}\n")
            
            return "\n".join(srt_content)
        else:
            raise Exception(f"API 调用失败: {res.code} - {res.message}")
            
    except Exception as e:
        raise e
    finally:
        # 清理临时转换的 wav 文件
        if temp_wav and os.path.exists(temp_wav) and temp_wav != audio_file_path:
            try:
                os.remove(temp_wav)
            except:
                pass
