<div align="center">
<img width="2560" height="1270" alt="GHBanner" src="https://github.com/Chrisqyf/AI-Audio-Video-Subtitle-Generator/blob/main/page_cn.png" />
</div>

# AI 视频/音频字幕生成器

**其他语言版本: [English](README.md), [中文](README_CN.md).**

一个基于 **阿里通义千问 (DashScope)** 语音大模型的 Web 应用，可以自动为您的音视频文件生成 SRT 字幕。

本项目使用 [Streamlit](https://streamlit.io/) 构建，界面简洁，支持一键部署。

## 功能特点
- 🎥 支持多种格式：MP4, MP3, WAV, M4A, FLAC 等。
- ⚡ 极速转写：使用 `paraformer-realtime-v1` 实时流式模型。
- 📝 标准输出：直接生成带时间戳的 `.srt` 字幕文件。
- ☁️ 云端部署：支持完全在浏览器中运行（手机/电脑通用）。

## 如何使用 (推荐)
直接点击下面的域名: 
https://ai-audio-video-subtitle-generator-ngwvqihgpqeb7pkrdop4ba.streamlit.app/

## 本地运行指南

1. **进入目录**:
   ```bash
   cd web_app
   ```

2. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```

3. **安装 FFmpeg** (必选):
   - 本地运行必须安装 FFmpeg 并配置好环境变量。
   - [FFmpeg 下载地址](https://ffmpeg.org/download.html)。

4. **启动应用**:
   ```bash
   streamlit run app.py
   ```
   浏览器会自动打开 `http://localhost:8501`。

## 如何免费部署到公网 (Streamlit Cloud)

本项目已针对 [Streamlit Cloud](https://streamlit.io/cloud) 进行了配置，可以免费部署供他人使用。

1. 将本文件夹的代码上传到您的 GitHub 仓库。
2. 注册并登录 Streamlit Cloud。
3. 点击 "New app"，选择对应的 GitHub 仓库。
4. 在设置中：
   - **Main file path** (主文件路径) 填入: `app.py`
5. 点击 **Deploy** (部署)。

*注意：项目中包含的 `packages.txt` 文件会自动处理云端的 FFmpeg 依赖，您无需手动配置。*

## 依赖要求
- Python 3.8+
- 阿里云 DashScope API Key (百炼控制台获取)


