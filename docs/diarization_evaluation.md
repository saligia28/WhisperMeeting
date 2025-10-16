# 说话人分离评估

| 方案 | 优点 | 缺点 | 适用场景 |
| --- | --- | --- | --- |
| `pyannote.audio` (`DiarizationService`) | 精度高、生态成熟 | 需下载额外模型、GPU 依赖重 | 多人会议准确分离 |
| `speechbrain` | 部署简单 | 中文数据优化不足 | 轻量级场景 |
| 声纹注册 + 比对 | 小规模固定参与人效果佳 | 需采集声纹库 | 固定团队会议 |

评估流程：
1. 使用 `MeetingPipeline` 生成转写，启用 `PostProcessingConfig.enable_speaker_diarization = True`。
2. 在 `docs/sample_annotations.json`（预留）对说话人进行人工标注，以 F1-score 对比算法输出。
3. 若 `pyannote` 延迟高，可切换为声纹注册模式，仅在识别错误时人工修正。

> 若同时启用源分离（`source_separation.md`），需先做声源划分，再喂给 Whisper。
