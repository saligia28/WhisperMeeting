# 架构总览

WhisperMeeting 采用模块化设计，便于按需替换 Whisper 模型、说话人分离模型或摘要模型。系统分为三层：

1. **数据采集层**：`AudioRecorder` 负责实时录音/分片，也支持离线音频上传。
2. **推理管线层**：`MeetingPipeline` 串联转写、后处理与摘要，`PostProcessor` 处理对齐、关键词和持久化。
3. **交付层**：FastAPI 暴露 REST 接口，CLI 用于命令行验证；前端草图见 `frontend.md`。

依赖关系由 `ServiceContainer` 维护，便于测试或替换实现。所有持久化统一走 `MeetingRepository`，存储结构见 `storage.md`。
