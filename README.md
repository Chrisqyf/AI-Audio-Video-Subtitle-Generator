# AI Audio/Video Subtitle Generator

**Read this in other languages: [English](README.md), [中文](README_CN.md).**

A simple web application powered by **Alibaba DashScope (Qwen/Paraformer)** to automatically generate SRT subtitles for your audio and video files.

Built with [Streamlit](https://streamlit.io/).

## Features
- 🎥 Support various formats: MP4, MP3, WAV, M4A, etc.
- ⚡ Fast transcription using DashScope's `paraformer-realtime-v1` model.
- 📝 Auto-generates standard `.srt` format with timestamps.
- ☁️ Easy deployment on cloud platforms.

## How to use (RECOMMEND)
Click this domain that created by Streamlit:
https://ai-audio-video-subtitle-generator-ngwvqihgpqeb7pkrdop4ba.streamlit.app/


## How to Run Locally

1. **Clone the repository** (or download the folder):
   ```bash
   cd web_app
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install FFmpeg**:
   - Make sure `ffmpeg` is installed on your system and added to your PATH.
   - [Download FFmpeg here](https://ffmpeg.org/download.html).

4. **Run the App**:
   ```bash
   streamlit run app.py
   ```
   The browser will open automatically at `http://localhost:8501`.

## How to Deploy on Streamlit Cloud (Free)

This project is optimized for [Streamlit Cloud](https://streamlit.io/cloud).

1. Push this folder to a GitHub repository.
2. Sign up/Login to Streamlit Cloud.
3. Click "New app" and select your repository.
4. Settings:
   - **Main file path**: `app.py`
5. Click **Deploy**.

*Note: The included `packages.txt` file ensures FFmpeg is installed in the cloud environment automatically.*

## Requirements
- Python 3.8+
- Alibaba Cloud DashScope API Key

