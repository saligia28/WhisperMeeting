# 会议助理可行性评估与TODO

## 可行性概览
- ✅ 如果使用 `faster-whisper` 或 ONNX 版本，Whisper 在常见消费级 CPU/GPU 上即可实现实时或准实时的会议转写；模型越大准确率越高，但也越吃资源。
- ✅ 本地大模型（如 Llama 3、Mistral）在经过量化并通过 `llama.cpp`、`vLLM` 等部署后，可以对转写结果做摘要和重点标注；按段批量处理可控制延迟。
- ✅ 通过轻量级后端（FastAPI、Node 等）协调推理流程，前端即可调用录音、查看进度并管理产出。
- ⚠️ 需关注硬件算力（显存/内存）、目标操作系统的音频设备权限，以及多模型同时运行时的响应性。

## 需要设计的核心模块
- 音频采集：系统或麦克风录音、可选的降噪、按 Whisper 友好的片段切分。
- 转写服务：Whisper/faster-whisper 任务，结合 VAD 做语音段落分割，可配置语言或翻译模式。
- 后处理管线：时间戳对齐、说话人分离（如 pyannote）、调用本地大模型做摘要/要点提取。
- 存储与检索：轻量数据库（SQLite/Postgres）或向量库，用于存储转写和摘要并支持搜索。
- 前端控制面板：Web 或桌面界面，支持开始/停止录音、查看实时字幕、标记重点、导出笔记。
- 自动化钩子：预约录音、与日历集成、稳定后输出到 Notion/Markdown 等。

## 风险与缓解
- Whisper 与大模型共用有限 GPU 时可能出现延迟峰值 → 考虑 Whisper 使用 CPU/小模型、大模型占用 GPU，或分阶段处理。
- 音频设备权限/平台差异 → 尽早在目标操作系统验证录音流程，必要时封装原生模块。
- 长时间会议导致内存压力 → 结果流式写盘，并在界面中分页展示。
- 全程离线会增加模型更新难度 → 需要提前规划模型管理和版本维护方案。

## 探讨记录
- 环境：MacBook Pro M1 Max 32GB 统一内存，Metal 后端可支撑 Whisper `medium`/`large-v2` 模型的实时或准实时推理。
- 工具链选择：`faster-whisper`（CTranslate2 + Metal）在准确率/性能/生态之间最均衡；`whisper.cpp` 做轻量命令行或离线部署；PyTorch 原版主要用于跟随官方最新特性。
- 说话人分离：Whisper 系列仅负责转写，需叠加 diarization 组件（如 `whisperx` + `pyannote.audio`、`speechbrain`、声纹比对）才能区分不同说话人；固定说话人可预注册声纹提升准确率。
- 混讲话处理：如需在多人同时发言时保持准确，需要额外的源分离模型（`pyannote/speaker-separation`、`demucs` 等），但会显著增加算力与延迟。
- 参考行业流程：外部方案常见工作流为“录音 → Whisper 转写 → 预处理 → GPT 分析 → 输出 → 回顾”，配合结构化 Prompt（需求表格、优先级、验收矩阵等）可直接生成交付物；若要离线化，可用本地 LLM（如 Qwen、Llama3）替代 GPT API，并用 Pandas/OpenPyXL、Notion/Jira API 完成自动化导出。

## TODO / 下一步
- [x] 评估目标硬件（CPU/GPU、内存、磁盘）是否能承载计划使用的 Whisper 模型和大模型。（参考 `scripts/evaluate_hardware.py` 与 `docs/hardware_evaluation.md`）
- [x] 选定工具链：优先验证 `faster-whisper`（Metal 支持 + Python 生态），同时保留 `whisper.cpp` 作为轻量备选；补充本地大模型服务框架、说话人分离库等。（见 `docs/toolchain.md`）
- [x] 设计后端 API，包括开始/停止录音、转写状态、摘要请求、结果下载等接口。（实现见 `src/whispermeeting/api/app.py` 与 `docs/api.http`）
- [x] 做命令行原型（音频片段 → 转写 → 摘要）验证两类模型的协同流程。（实现见 `src/whispermeeting/cli.py`）
- [x] 绘制前端交互草图，包括控制按钮、实时字幕、标记/摘要视图。（见 `docs/frontend.md`）
- [x] 确定存储结构（原始音频、片段、转写、摘要、重点）和保留策略。（见 `docs/storage.md` 与 `src/whispermeeting/storage/repository.py`）
- [x] 制定测试与监控方案（各阶段单测、延迟监控、用户验收流程）。 （见 `docs/testing_strategy.md` 与 `tests/`）
- [x] 评估说话人分离方案：对比 `whisperx`（含 `pyannote.audio`）与 `speechbrain` 或声纹注册流程，在本地录音样本上验证准确率与延迟。（见 `docs/diarization_evaluation.md` 与 `src/whispermeeting/pipeline/diarization.py`）
- [x] 调研必要时的源分离方案（如 `demucs`）对实时性影响，决定是否纳入 MVP。（见 `docs/source_separation.md`）
- [x] 设计需求分析自动化：基于结构化 Prompt 的表格输出流程，测试本地 LLM/ChatGPT 生成需求拆解、优先级与验收矩阵的可行性，并规划导出 Notion/Jira 的脚本。（见 `docs/automation.md` 与 `src/whispermeeting/llm/summarizer.py`）

## 性能问题与代码冗余（待优化）

### 🔴 严重性能问题

1. **ServiceContainer 每次请求都重建** (`src/whispermeeting/api/app.py:31-32`)
   - **问题描述**：`get_container()` 依赖注入函数每次API请求都调用 `build_container()`，导致：
     - WhisperModel 每次请求都重新加载（模型加载耗时数秒到数十秒）
     - LocalLLMSummariser 每次都重新初始化（可能加载大模型）
     - 数据库引擎重复创建
   - **影响**：API响应极慢，资源浪费严重，无法支撑并发请求
   - **解决方案**：使用 FastAPI 的 lifespan context manager 或全局单例模式管理 ServiceContainer
   - **优先级**：P0 - 立即修复

2. **转写接口缺少异步处理机制** (`src/whispermeeting/api/app.py:146-181`)
   - **问题描述**：`POST /meetings/{id}/transcribe` 在同步端点中执行耗时的转写和摘要操作
   - **影响**：
     - 长音频（>5分钟）会导致请求超时
     - 阻塞工作线程，降低整体并发能力
     - 用户体验差，无法获取进度反馈
   - **解决方案**：
     - 方案A：使用 FastAPI BackgroundTasks
     - 方案B：引入 Celery/RQ 任务队列
     - 添加任务状态查询接口 `GET /meetings/{id}/status`
   - **优先级**：P0 - 立即修复

3. **重复的数据库查询** (`src/whispermeeting/api/app.py:162-171`)
   - **问题描述**：`pipeline.run()` 返回的 transcript 已包含 segments，但紧接着又调用 `repository.get_transcript_segments()` 重新查询
   - **影响**：不必要的数据库往返，增加响应延迟
   - **解决方案**：直接使用 `output.transcript.segments` 构建响应
   - **优先级**：P1 - 近期修复

### 🟡 中等性能问题

4. **临时文件清理不完善** (`src/whispermeeting/api/app.py:154-160`)
   - **问题描述**：
     - 转写失败时，上传的原始文件可能没有被清理
     - `transcribe_chunk` 的 WAV 转换失败时文件清理逻辑不健全
   - **影响**：长期运行会导致磁盘空间泄漏
   - **解决方案**：使用 `try-finally` 或 context manager 确保临时文件总是被清理
   - **优先级**：P1 - 近期修复

5. **数据库连接池配置缺失** (`src/whispermeeting/storage/repository.py:45`)
   - **问题描述**：
     - SQLModel engine 使用默认连接池配置
     - 高并发时可能导致连接池耗尽
   - **解决方案**：
     - 配置 `pool_size`、`max_overflow`、`pool_pre_ping`
     - 考虑使用异步 SQLModel（`asyncpg`）
   - **优先级**：P2 - 后续优化

6. **关键词提取算法效率低** (`src/whispermeeting/pipeline/postprocessing.py:60-69`)
   - **问题描述**：
     - 简单的词频统计，没有停用词过滤
     - 每次调用都重新计算，没有缓存
     - 对长会议（数千个segment）性能差
   - **解决方案**：
     - 引入中文停用词表
     - 使用更高效的算法（TF-IDF、TextRank）
     - 对结果进行缓存
   - **优先级**：P2 - 后续优化

### 🔵 代码冗余问题

7. **Segment 序列化代码重复** (`src/whispermeeting/api/app.py`)
   - **位置**：133-143行、163-171行、217-225行
   - **问题**：三个端点都有相同的 segment 转换为 dict 的逻辑
   - **解决方案**：提取为 `_serialize_segments(segments: list[TranscriptSegment], offset: float = 0.0) -> list[dict]`
   - **优先级**：P2

8. **音频文件处理逻辑重复** (`src/whispermeeting/api/app.py`)
   - **位置**：103-131行（transcribe_chunk）、146-160行（transcribe_meeting）
   - **重复内容**：
     - 创建上传目录
     - 写入上传文件
     - WAV格式转换
     - 临时文件清理
   - **解决方案**：提取为 `async def _prepare_audio(upload: UploadFile, target_dir: Path, cleanup_on_error: bool = True) -> Path`
   - **优先级**：P2

9. **Meeting 创建/更新逻辑分散** (`src/whispermeeting/storage/repository.py`)
   - **位置**：48-62行（save_transcript）、126-138行（create_meeting）
   - **问题**：两个方法都有创建或更新 Meeting 的逻辑，容易不一致
   - **解决方案**：统一为 `_upsert_meeting()` 私有方法
   - **优先级**：P3

10. **硬编码的音频参数** (`src/whispermeeting/api/app.py:72`)
    - **问题**：FFmpeg 参数 `"-ar", "16000", "-ac", "1"` 硬编码在代码中
    - **解决方案**：添加到 `TranscriptionConfig` 或 `ApiConfig` 中
    - **优先级**：P3

### 🟢 架构增强建议

11. **缺少缓存层**
    - **问题**：频繁访问的会议摘要、转写结果都直接查询数据库/文件系统
    - **解决方案**：
      - 引入 Redis 或内存缓存（`cachetools`、`functools.lru_cache`）
      - 缓存已完成会议的摘要和转写结果
    - **优先级**：P3

12. **缺少 API 限流机制**
    - **问题**：转写是重操作，无限制并发会耗尽 GPU/CPU 资源
    - **解决方案**：
      - 使用 `slowapi` 或 `fastapi-limiter` 限制请求频率
      - 限制同时进行的转写任务数量
    - **优先级**：P2

13. **日志系统不完善**
    - **问题**：只有 `print()` 输出，没有结构化日志
    - **解决方案**：
      - 引入 `structlog` 或 Python `logging` 模块
      - 记录转写耗时、API响应时间、错误堆栈
      - 添加请求追踪 ID
    - **优先级**：P2

14. **缺少性能监控指标**
    - **问题**：无法监控系统性能和资源使用
    - **解决方案**：
      - 添加 `/metrics` 端点（Prometheus格式）
      - 监控指标：转写队列长度、平均处理时间、GPU利用率、内存使用
      - 使用 `prometheus-fastapi-instrumentator`
    - **优先级**：P3

15. **异常处理不一致**
    - **问题**：
      - 有些地方用通用 `Exception`，有些用 `HTTPException`
      - 错误消息格式不统一（中英文混用）
    - **解决方案**：
      - 定义统一的异常处理器（`@app.exception_handler`）
      - 创建自定义异常类体系
      - 统一错误响应格式（包含 code、message、details）
    - **优先级**：P2
