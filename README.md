<div align="center">

<img src="/docs/logo.png" alt="VideoLingo Logo" height="140">

# Connect the World, Frame by Frame

<a href="https://trendshift.io/repositories/12200" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12200" alt="Huanshere%2FVideoLingo | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[**English**](/README.md)｜[**简体中文**](/translations/README.zh.md)｜[**繁體中文**](/translations/README.zh-TW.md)｜[**日本語**](/translations/README.ja.md)｜[**Español**](/translations/README.es.md)｜[**Русский**](/translations/README.ru.md)｜[**Français**](/translations/README.fr.md)

</div>

---

## 📌 本 Fork 的改动（beiyenan/VideoLingo）

本仓库基于 [Huanshere/VideoLingo](https://github.com/Huanshere/VideoLingo)，目标是把**语音识别放到云端**、**配音留在本地**，让 8GB 显存的机器不必在 ASR 与 TTS 之间来回抢显存，同时全程零配音 API 费用。

> 下方内容为上游原始文档，未作改动。

### 新增：SiliconFlow 云端语音识别

- **模型**：`XingChenAGI/XingChenASR-V3.2-Ultra`（免费层），侧边栏 `语音识别运行环境` 选择 `SiliconFlow（云端）`
- **为什么**：本地 Qwen3-ASR 会占用显存，与本地 TTS 冲突。云端识别后 GPU 只需服务配音
- **配置**：`api.key` 填 SiliconFlow API Key，或留空回退到环境变量 `SILICONFLOW_API_KEY`
- **注意**：音频会上传到 SiliconFlow；该免费模型不产生费用

### 新增：本地 VoxCPM2 配音

- **模型**：[VoxCPM2](https://github.com/OpenBMB/VoxCPM)（2B，48kHz，支持音色克隆与跨语言克隆）
- **常驻 worker**：模型只加载一次，整个视频复用。重启后第一句约 30 秒加载，之后每句约 10 秒
- **安装目录**：通过配置项 `voxcpm.root` 指定（含 `models/` 和 `venv/` 的那一层文件夹），也可在侧边栏填写

#### 参考音频模式（关键）

VoxCPM2 需要一段参考音频来克隆音色。**留空时模型会为每一句随机采样一个新说话人**，听起来就是「每句配音都是不同的人」。侧边栏 `参考音频模式` 提供四个选项：

| 模式 | 参考来源 | 适用场景 |
|---|---|---|
| **1** | 你自己指定的音频文件（`voxcpm.reference_wav`） | 想要一个固定「主播音色」，配任何片子都是同一人 |
| **2**（默认） | 本视频的第一段人声（`output/audio/refers/1.wav`） | 每个视频自动获得自己的音色，**换视频无需改配置** |
| **3** | 每句用它自己那段的原声（`output/audio/refers/<序号>.wav`） | 多人对话 / 访谈类，保住各自说话人的音色 |
| **4** | 不使用参考音频 | 排查问题用 |

模式 2、3 依赖「提取参考音频」步骤生成的片段；若目录为空会**明确报错**而非静默降级。

### 修复

| 问题 | 原因 |
|---|---|
| 长视频只译出零星几句 | SiliconFlow 只返回句级时间戳，`process_transcription()` 把整句当作一个「词」，被 30 字符上限静默丢弃。现已按字符比例合成词级时间戳 |
| 字幕对不上时间轴 | 云端返回的每段带引号，与下游匹配逻辑不一致。现已在 ASR 层统一归一化 |
| 字幕匹配失败 (`No match found for sentence`) | 词级与句级用了不同的归一化函数。现共用同一个 `_match_key()` |
| API Key 在页面上明文显示 | 密钥输入框改为掩码显示 |

### 其他

- 侧边栏中文文案补全（`translations/zh-CN.json`），避免漏译时静默退回英文
- `config.yaml` 中 API Key 均为占位符，请填入你自己的 Key（**不要把真实 Key 提交到仓库**）

### Windows 一键启动

双击项目根目录下的 **`run_portable.bat`** 即可：它从脚本自身位置推算项目路径，因此放在任意目录都能用
（需与 `start.py` 放在同一层）。它会：

1. 探测服务是否已在运行 —— 已在跑就直接打开网页，不会重复启动
2. 后台等待服务就绪后自动打开浏览器（不是死等固定秒数）
3. 找不到 `uv` 或放错目录时给出明确提示，而不是一闪而过

```bat
:: 端口固定在 .streamlit\config.toml，不要用命令行传
:: uv run --port 8501 ... 会被 uv 拒绝：error: unexpected argument '--port'
```

在 PowerShell 里启动可用 `.\run_portable.bat`。

---

## 🌟 Overview ([Try VL Now!](https://videolingo.io))

VideoLingo combines speech recognition, subtitle translation, segmentation and dubbing in a Streamlit interface. It produces subtitle files and optionally subtitled or dubbed videos. Translation quality depends on the source audio, language and chosen models.

Key features:
- 🎥 YouTube video download via yt-dlp

- Word-level speech recognition and alignment with Qwen3-ASR + Qwen3-ForcedAligner

- **📝 NLP and AI-powered subtitle segmentation**

- **📚 Custom + AI-generated terminology for coherent translation**

- Direct translation with optional reflection and natural rewriting

- Subtitle segmentation with configurable length limits

- **🗣️ Dubbing with GPT-SoVITS, OpenAI, Edge TTS, and more**

- 🚀 One-click startup and processing in Streamlit

- 🌍 Multi-language support in Streamlit UI

- 📝 Detailed logging with progress resumption

- 🔍 Model searchbox with API auto-fetch — search and filter from your provider's full model list

- ⏯️ Task control — pause, resume, or stop processing at any step

The workflow combines transcription, translation, subtitle layout and dubbing in one project.

## 🎥 Demo

<table>
<tr>
<td width="33%">

### Dual Subtitles
---
https://github.com/user-attachments/assets/a5c3d8d1-2b29-4ba9-b0d0-25896829d951

</td>
<td width="33%">

### Cosy2 Voice Clone
---
https://github.com/user-attachments/assets/e065fe4c-3694-477f-b4d6-316917df7c0a

</td>
<td width="33%">

### GPT-SoVITS with my voice
---
https://github.com/user-attachments/assets/47d965b2-b4ab-4a0b-9d08-b49a7bf3508c

</td>
</tr>
</table>

### Language Support

**Input languages:**

🇺🇸 English 🤩 | 🇷🇺 Russian 😊 | 🇫🇷 French 🤩 | 🇩🇪 German 🤩 | 🇮🇹 Italian 🤩 | 🇪🇸 Spanish 🤩 | 🇯🇵 Japanese 😊 | 🇨🇳 Chinese 🤩

Dubbing languages depend on the selected TTS method.

## Installation

VideoLingo supports Windows, macOS (Apple Silicon / Intel), and Linux.

### Ask your local AI agent 🤖

If you use an AI agent that can operate your computer, send it this prompt:

> Install and launch GitHub's Huanshere/VideoLingo on my computer.

### Windows: one-click install 🎉

1. Download **Source code (zip)** from the [latest Release](https://github.com/Huanshere/VideoLingo/releases/latest), extract it to your Desktop or another folder, and open the folder.
2. Double-click `OneKeyStart.bat` and keep the window open. On the first run, it automatically installs uv, Python 3.12, the app dependencies, and FFmpeg. An internet connection is required.
3. After installation, VideoLingo opens automatically in your browser. Enter your API URL, key, and model in the sidebar to start using it.

### Install from source (Windows, macOS, Linux)

```bash
git clone https://github.com/Huanshere/VideoLingo.git && cd VideoLingo
uv run start.py
```

To start it later, run `uv run start.py` again from the VideoLingo folder. Apple Silicon uses MLX; Intel Macs use CPU recognition. By default, Intel Mac dubbing uses the new voice without the original background sound.

#### Docker (optional)

For a Linux NVIDIA container deployment, install Docker, a compatible GPU driver and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). The image uses the same Python 3.12 setup and application dependencies, with CUDA 12.8.1/cu128 by default. See [Docker docs](/docs/pages/docs/docker.en-US.md) for the matched CUDA 12.6 alternative and persistence settings.

```bash
docker build -t videolingo .
docker run -d -p 8501:8501 --gpus all videolingo
```

## HTTP API (replaces Excel batch mode)

For agents and scripts, use the local HTTP API instead of the former Excel batch mode.
It shares the Streamlit pipeline and processes one operation at a time using `output/`.
Configure `config.yaml` and start it from the project root. The command also installs missing dependencies on first use:

```bash
uv run start.py --api
```

See the **[HTTP API guide](docs/api.md)** for input, processing, progress, downloads,
retries and serial batch processing. Interactive endpoint docs: [localhost:8000/docs](http://localhost:8000/docs).

## LLM, ASR and TTS providers
VideoLingo supports OpenAI-Like API format and various TTS interfaces:
- LLM: choose an OpenAI-compatible Chat Completions provider and model that can return the structured JSON required by the workflow. [OpenLux](https://www.openlux.ai/register?aff=wKYu) is recommended; set the API URL to `https://api.openlux.ai/v1`. Prefer GPT-6 Luna with model ID `gpt-6-luna` for best value, GPT-6 Sol with `gpt-6-sol` for better quality, or Claude Opus 5.5 with `claude-opus-5-5` for best quality. OpenLux relay rates are in the install docs. Configure the API URL, key and model in the sidebar.
- Speech recognition: run Qwen3-ASR + ForcedAligner locally (default), or choose SiliconFlow cloud ASR, ElevenLabs or MAI-Transcribe-2 in the sidebar. MAI supports an Azure Speech key or an OpenRouter key entered in the sidebar; audio is sent to the selected provider and may incur charges. WhisperX is not installed by the installer; to use it as a backend, follow [WhisperX (manual install)](docs/pages/docs/whisperx-manual.en-US.md).
- TTS: OpenAI, Fish Audio, SiliconFlow Fish/CosyVoice2, GPT-SoVITS, Edge TTS, F5-TTS, local VoxCPM2 (this fork) and a custom adapter in `core/tts_backend/custom_tts.py`.

For detailed installation, LLM configuration, and usage instructions, please refer to the documentation: [English](/docs/pages/docs/start.en-US.md) | [中文](/docs/pages/docs/start.zh-CN.md)

## Current Limitations

1. Background noise and language-specific alignment models affect recognition and word timestamps. Vocal separation may help. Numbers and symbols may lack reliable word timings; inspect the resulting subtitles.

2. LLM output must satisfy the workflow's JSON structure. For failures, inspect `output/gpt_log/error.json`. Existing successful response caches and completed outputs can be reused on retry; changing the model alone does not regenerate every completed stage. Do not delete all output as the first troubleshooting step.

3. Dubbing quality and timing depend on translation, the TTS service and speech rate. Speed adjustment does not guarantee natural delivery or perfect synchronization.

4. Local recognition uses one primary recognition/alignment language per audio segment. Mixed-language speech is not guaranteed to retain accurate text and timing in every language.

5. The dubbing workflow does not automatically assign a separate voice to each speaker.

## 📄 License

This project is licensed under the Apache 2.0 License. Special thanks to the following open source projects for their contributions:

[Qwen3-ASR](https://github.com/Qwen/Qwen3-ASR), [MLX Audio](https://github.com/Blaizzy/mlx-audio), [whisperX](https://github.com/m-bain/whisperX), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [json_repair](https://github.com/mangiucugna/json_repair), [BELLE](https://github.com/LianjiaTech/BELLE)

## 📬 Contact Me

- Submit [Issues](https://github.com/Huanshere/VideoLingo/issues) or [Pull Requests](https://github.com/Huanshere/VideoLingo/pulls) on GitHub
- DM me on Twitter: [@Huanshere](https://twitter.com/Huanshere)
- Email me at: team@videolingo.io

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Huanshere/VideoLingo&type=Timeline)](https://star-history.com/#Huanshere/VideoLingo&Timeline)

---

<p align="center">If you find VideoLingo helpful, please give me a ⭐️!</p>
