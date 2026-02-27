import streamlit as st
import os
import shutil
from audio_processor import generate_srt

# --- 页面配置 ---
st.set_page_config(
    page_title="AI 字幕生成器",
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

# --- 标题和介绍 ---
st.title("🎙️ AI 视频/音频字幕生成器")
st.markdown("""
使用阿里通义千问 (Qwen/Paraformer) 语音大模型，快速为您的音视频生成 **SRT 字幕文件**。
支持 MP4, MP3, WAV, M4A 等常见格式。
""")

# --- 侧边栏：API Key 配置 ---
with st.sidebar:
    st.header("⚙️ 设置")
    api_key = st.text_input(
        "DashScope API Key", 
        type="password",
        help="请前往阿里云 DashScope 控制台获取 API Key"
    )
    st.markdown("---")
    st.markdown("""
    **如何获取 Key?**
    1. 注册/登录 [阿里云百炼控制台](https://bailian.console.aliyun.com/)
    2. 创建 API Key
    3. 粘贴到上方输入框
    """)
    st.markdown("---")
    st.caption("🔒 您的 Key 仅用于当前会话，不会被保存。")

# --- 主逻辑区域 ---

# 1. 文件上传
uploaded_file = st.file_uploader(
    "📂 请拖入或选择视频/音频文件", 
    type=['mp4', 'mp3', 'wav', 'm4a', 'flac', 'mov', 'avi']
)

if uploaded_file:
    # 显示文件信息
    st.info(f"已选择文件: **{uploaded_file.name}** ({uploaded_file.size / 1024 / 1024:.2f} MB)")
    
    # 2. 检查 API Key
    if not api_key:
        st.warning("👈 请先在左侧侧边栏输入 DashScope API Key")
    else:
        # 3. 开始处理按钮
        if st.button("🚀 开始生成字幕"):
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
                status_text.text("正在保存文件...")
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                progress_bar.progress(10)
                
                # 调用处理逻辑
                status_text.text("正在进行 AI 语音识别 (可能需要几分钟，请勿关闭页面)...")
                progress_bar.progress(30)
                
                # 核心处理
                srt_result = generate_srt(file_path, api_key)
                
                progress_bar.progress(90)
                status_text.text("处理完成！正在准备下载...")
                
                # 显示成功信息
                st.success("✅ 字幕生成成功！")
                progress_bar.progress(100)
                
                # 展示部分结果预览
                with st.expander("📄 字幕内容预览 (前 500 字符)"):
                    st.text(srt_result[:500] + "..." if len(srt_result) > 500 else srt_result)
                
                # 4. 下载按钮
                video_name = os.path.splitext(uploaded_file.name)[0]
                st.download_button(
                    label="⬇️ 下载 .SRT 字幕文件",
                    data=srt_result,
                    file_name=f"{video_name}.srt",
                    mime="text/plain"
                )
                
            except Exception as e:
                st.error(f"❌ 发生错误: {str(e)}")
                st.markdown("**常见排查:**\n1. API Key 是否有效？\n2. 音频是否包含清晰的人声？\n3. 文件格式是否受损？")
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
    st.info("👆 请先在上方上传文件")

# --- 页脚 ---
st.markdown("---")
st.caption("Powered by Alibaba DashScope | Built with Streamlit")
