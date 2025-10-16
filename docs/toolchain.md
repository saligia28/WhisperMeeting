# 工具链选择

| 模块 | 首选方案 | 备选方案 | 备注 |
| --- | --- | --- | --- |
| 转写 | `faster-whisper` + CTranslate2 | `whisper.cpp`, OpenAI Whisper | Metal/MPS 支持良好，可切换 CPU/GPU |
| 说话人分离 | `pyannote.audio` | `speechbrain`、声纹注册 | 提供 `DiarizationService` 接口 |
| 摘要 | `llama-cpp-python` + 本地 LLM | `transformers` summarization pipeline | 支持结构化 JSON 输出 |
| 源分离 | `demucs`（可选） | `pyannote/speaker-separation` | 按需在多说话人重叠场景启用 |
| 存储 | SQLite (`sqlmodel`) | Postgres | 默认 SQLite，易于部署 |
| 后端 | FastAPI | Node.js + Express | 轻量、支持 async |
| 前端 | Vite + React | Tauri、Electron | 草图基于 Web，后续可转桌面 |

> 详见 `automation.md`，描述将摘要导出至 Notion/Jira 的脚本计划。
