import streamlit as st
import os
import shutil
from audio_processor import generate_srt

# --- 多语言配置 ---
TRANSLATIONS = {
    "page_title": {
        "CN": "🎙️ AI 视频/音频字幕生成器",
        "EN": "🎙️ AI Video/Audio Subtitle Generator"
    },
    "page_intro": {
        "CN": """
使用阿里通义千问 (Qwen/Paraformer) 语音大模型，快速为您的音视频生成 **SRT 字幕文件**。
支持 MP4, MP3, WAV, M4A 等常见格式。
""",
        "EN": """
Generate **SRT subtitles** for your audio/video files instantly using Alibaba DashScope (Qwen/Paraformer) speech models.
Supports MP4, MP3, WAV, M4A, and more.
"""
    },
    "sidebar_header": {
        "CN": "⚙️ 设置",
        "EN": "⚙️ Settings"
    },
    "api_key_label": {
        "CN": "DashScope API Key",
        "EN": "DashScope API Key"
    },
    "api_key_help": {
        "CN": "请前往阿里云 DashScope 控制台获取 API Key",
        "EN": "Get your API Key from Alibaba Cloud DashScope Console"
    },
    "api_key_guide": {
        "CN": """
    **如何获取 Key?**
    1. 注册/登录 [阿里云百炼控制台](https://bailian.console.aliyun.com/)
    2. 创建 API Key
    3. 粘贴到上方输入框
    """,
        "EN": """
    **How to get a Key?**
    1. Register/Login [Alibaba Bailian Console](https://bailian.console.aliyun.com/)
    2. Create API Key
    3. Paste into the input box above
    """
    },
    "api_key_warning": {
        "CN": "🔒 您的 Key 仅用于当前会话，不会被保存。",
        "EN": "🔒 Your Key is used for this session only and not saved."
    },
    "upload_label": {
        "CN": "📂 请拖入或选择视频/音频文件",
        "EN": "📂 Drag and drop or select video/audio file"
    },
    "file_upload_info": {
        "CN": "已选择文件: **{name}** ({size:.2f} MB)",
        "EN": "Selected file: **{name}** ({size:.2f} MB)"
    },
    "warning_input_key": {
        "CN": "👈 请先在左侧侧边栏输入 DashScope API Key",
        "EN": "👈 Please enter DashScope API Key in the sidebar first"
    },
    "start_btn": {
        "CN": "🚀 开始生成字幕",
        "EN": "🚀 Start Generating Subtitles"
    },
    "status_saving": {
        "CN": "正在保存文件...",
        "EN": "Saving file..."
    },
    "status_processing": {
        "CN": "正在进行 AI 语音识别 (可能需要几分钟，请勿关闭页面)...",
        "EN": "Processing AI speech recognition (may take minutes, please keep page open)..."
    },
    "status_preparing_download": {
        "CN": "处理完成！正在准备下载...",
        "EN": "Done! Preparing download..."
    },
    "success_msg": {
        "CN": "✅ 字幕生成成功！",
        "EN": "✅ Subtitles generated successfully!"
    },
    "preview_label": {
        "CN": "📄 字幕内容预览 (前 500 字符)",
        "EN": "📄 Subtitle Preview (first 500 chars)"
    },
    "download_btn": {
        "CN": "⬇️ 下载 .SRT 字幕文件",
        "EN": "⬇️ Download .SRT Subtitle File"
    },
    "error_prefix": {
        "CN": "❌ 发生错误: ",
        "EN": "❌ Error occurred: "
    },
    "error_tips": {
        "CN": "**常见排查:**\n1. API Key 是否有效？\n2. 音频是否包含清晰的人声？\n3. 文件格式是否受损？",
        "EN": "**Troubleshooting:**\n1. Is API Key valid?\n2. Does audio contain clear human voice?\n3. Is file format corrupted?"
    },
    "info_upload_first": {
        "CN": "👆 请先在上方上传文件",
        "EN": "👆 Please upload a file above first"
    }
}

# --- 页面配置 ---
st.set_page_config(
    page_title="AI 字幕生成器 / AI Subtitle Generator",
    page_icon="🎙️",
    layout="centered"
)

# --- 样式调整 ---
st.markdown("""
    <style>
    .main {
        padding-top: 2rem;
    }
    .stButton>button {
        width: 100%;
        background-color: #ff4b4b;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# --- 侧边栏：语言选择和设置 ---
with st.sidebar:
    # 语言选择
    lang_code = st.radio("Language / 语言", options=["中文", "English"], horizontal=True)
    lang = "CN" if lang_code == "中文" else "EN"

    st.header(TRANSLATIONS["sidebar_header"][lang])
    api_key = st.text_input(
        TRANSLATIONS["api_key_label"][lang], 
        type="password",
        help=TRANSLATIONS["api_key_help"][lang]
    )
    st.markdown("---")
    st.markdown(TRANSLATIONS["api_key_guide"][lang])
    st.markdown("---")
    st.caption(TRANSLATIONS["api_key_warning"][lang])

# --- 标题和介绍 ---
st.title(TRANSLATIONS["page_title"][lang])
st.markdown(TRANSLATIONS["page_intro"][lang])

# --- 主逻辑区域 ---

# 1. 文件上传
uploaded_file = st.file_uploader(
    TRANSLATIONS["upload_label"][lang], 
    type=['mp4', 'mp3', 'wav', 'm4a', 'flac', 'mov', 'avi']
)

if uploaded_file:
    # 显示文件信息
    st.info(TRANSLATIONS["file_upload_info"][lang].format(name=uploaded_file.name, size=uploaded_file.size / 1024 / 1024))
    
    # 2. 检查 API Key
    if not api_key:
        st.warning(TRANSLATIONS["warning_input_key"][lang])
    else:
        # 3. 开始处理按钮
        if st.button(TRANSLATIONS["start_btn"][lang]):
            # 创建进度条和状态占位符
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 创建临时目录保存文件
            temp_dir = "temp_uploaddir"
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            file_path = os.path.join(temp_dir, uploaded_file.name)
            
            try:
                # 保存上传文件到本地
                status_text.text(TRANSLATIONS["status_saving"][lang])
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                progress_bar.progress(10)
                
                # 调用处理逻辑
                status_text.text(TRANSLATIONS["status_processing"][lang])
                progress_bar.progress(30)
                
                # 核心处理
                srt_result = generate_srt(file_path, api_key)
                
                progress_bar.progress(90)
                status_text.text(TRANSLATIONS["status_preparing_download"][lang])
                
                # 显示成功信息
                st.success(TRANSLATIONS["success_msg"][lang])
                progress_bar.progress(100)
                
                # 展示部分结果预览
                with st.expander(TRANSLATIONS["preview_label"][lang]):
                    st.text(srt_result[:500] + "..." if len(srt_result) > 500 else srt_result)
                
                # 4. 下载按钮
                video_name = os.path.splitext(uploaded_file.name)[0]
                st.download_button(
                    label=TRANSLATIONS["download_btn"][lang],
                    data=srt_result,
                    file_name=f"{video_name}.srt",
                    mime="text/plain"
                )
                
            except Exception as e:
                st.error(f"{TRANSLATIONS['error_prefix'][lang]}{str(e)}")
                st.markdown(TRANSLATIONS["error_tips"][lang])
            finally:
                # 清理临时文件
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
                # 清理临时目录 (只有当空的时候)
                try:
                    os.rmdir(temp_dir)
                except:
                    pass
                # 移除进度条
                # progress_bar.empty()

else:
    # 引导提示
    st.info(TRANSLATIONS["info_upload_first"][lang])

# --- 页脚 ---
st.markdown("---")
st.caption("Powered by Alibaba DashScope | Built with Streamlit")
