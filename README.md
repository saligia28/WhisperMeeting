# WhisperMeeting

WhisperMeeting 是一个本地优先的会议助理原型，围绕 TODO 中的需求打造，覆盖从音频采集、转写、后处理到摘要与存储的完整流程。所有模块均可单独运行，方便在不同硬件环境下验证性能。

## 主要能力

- FastAPI 后端提供录音、转写、摘要、下载等接口。
- 支持按音频块实时上传 (`/meetings/{id}/transcribe/chunk`)，前端可在录音时显示即时字幕。
- CLI 原型可对单个音频文件执行“片段 → 转写 → 摘要”的串联流程。
- 模块化设计，涵盖音频采集、转写、说话人分离、摘要、存储等组件，便于替换具体实现。
- 提供硬件评估脚本和测试计划，帮助验证目标环境的可行性。

## 环境要求

- Python >= 3.9（推荐 3.10/3.11，先通过 `python3 --version` 或 `py --version` 确认版本）
- FFmpeg：用于音频预处理与格式转换  
  - macOS：`brew install ffmpeg`
  - Ubuntu/Debian：`sudo apt-get install ffmpeg`
  - Windows：可使用 [ffmpeg.org](https://ffmpeg.org/download.html) 的预编译包或 `choco install ffmpeg`
- PortAudio：`sounddevice` 依赖麦克风 / 扬声器驱动  
  - macOS：`brew install portaudio`
  - Ubuntu/Debian：`sudo apt-get install portaudio19-dev`
  - Windows：安装 `sounddevice` 会自带 DLL，如需录音支持可额外安装 [PortAudio binaries](http://files.portaudio.com/download.html)
- （可选）GPU 加速：根据 [PyTorch 官网](https://pytorch.org/get-started/locally/) 选择匹配硬件的 wheel 并在虚拟环境中安装

> 如位于中国大陆，可提前配置 PyPI 镜像（例如 `pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple`）以加速大体积依赖下载。

## 安装步骤

1. 创建虚拟环境

   ```bash
   python3 -m venv .venv        # macOS / Linux
   ```

   ```powershell
   py -3 -m venv .venv          # Windows PowerShell
   ```

2. 激活虚拟环境

   - macOS / Linux：`source .venv/bin/activate`
   - Windows PowerShell：`.venv\Scripts\Activate.ps1`
   - Windows CMD：`.venv\Scripts\activate.bat`

3. 升级基础工具（可选但推荐）

   ```bash
   pip install --upgrade pip setuptools wheel
   ```

4. 安装项目依赖

   ```bash
   pip install -e .
   ```

   如果需要运行测试和代码规范检查，可一次性安装开发依赖：

   ```bash
   pip install -e .[dev]
   ```

5. 首次安装完成后，可执行 `pip freeze > requirements.lock` 记录当前环境，便于部署或团队同步。

## 运行与调试

- 启动 FastAPI 后端（默认监听 8000 端口，若端口被占用会自动递增查找）：

  ```bash
  python -m whispermeeting.api.server --reload
  ```

  如需指定起始端口或搜索范围，可传入 `--port 9000 --port-search-limit 50`，脚本会输出最终使用的端口。

- 兼容传统 `uvicorn` 命令（无自动端口探测）：

  ```bash
  uvicorn whispermeeting.api.app:app --reload
  ```

- 默认摘要后端使用内置的 `stub` 提供商，可在 `.env` 或配置中切换 `summariser.provider` 为 `llama_cpp` / `transformers` 以启用真实模型（需准备对应依赖和模型文件）。

  启动后可参考 `docs/api.http` 的示例请求，或访问 `http://127.0.0.1:8000/docs` 使用 Swagger UI。

- 运行 CLI 原型，对单个音频执行转写与摘要：

  ```bash
  python -m whispermeeting.cli --input path/to/audio.wav --out-dir ./data/output
  ```

- 执行测试与静态检查（需安装开发依赖）：

  ```bash
  pytest
  ruff check src
  ```

- 硬件能力评估脚本位于 `scripts/evaluate_hardware.py`，可在虚拟环境中运行以验证目标机的实时转写能力。
- 需要快速准备演示数据，可执行 `python scripts/seed_demo_data.py`，它会往本地 SQLite 中注入一条示例会议记录与摘要。
- 欲搭配前端使用真实接口，可调用 `POST /meetings` 创建会议，再通过 `/meetings/{id}/transcribe` 上传音频；更多示例见 `docs/api.http`。
- 若需实时字幕，可在录音过程中持续请求 `POST /meetings/{id}/transcribe/chunk?offset=<秒>` 上传短音频片段，返回即时字幕片段后在前端拼接。

## 快速验证

完成安装后，可在激活的虚拟环境中运行以下命令确认核心依赖加载正常：

```bash
python -c "import torch, fastapi, whispermeeting; print('✅ whispermeeting ready')"
```

若出现依赖缺失或动态库错误，请回到“环境要求”章节检查系统级依赖是否安装完整。

## 项目结构

```
src/whispermeeting/
├── api/               # FastAPI 接口
├── audio/             # 音频采集与预处理
├── pipeline/          # 转写、摘要与后处理
├── storage/           # 数据持久化
├── llm/               # 本地大模型封装
├── utils/             # 通用工具
└── cli.py             # 命令行原型
```

完整的架构设计、测试策略与前端草图请见 `docs/` 目录。

## 后续迭代方向

- 接入真实的实时字幕流（WebSocket / SSE），替换当前基于异步轮询的刷新机制。
- 将重点标记、摘要等数据通过新接口（例如 `/meetings/{id}/highlights`）持久化，支持团队协作。
- 把 `summariser.provider` 切换到 `llama_cpp` 或 `transformers`，结合本地或推理服务的模型提升摘要质量。
- 说话人分离目前默认关闭。未来如需启用，请准备 Hugging Face Access Token、安装 FFmpeg 与 `pyannote.audio` 对应依赖，然后将 `postprocessing.enable_speaker_diarization` 设为 `true` 即可恢复该能力。
