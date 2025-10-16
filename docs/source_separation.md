# 源分离调研

- `demucs`：深度学习源分离，准确率高，但需要 GPU；建议仅在多人重叠严重的会议中启用。
- `pyannote/speaker-separation`：与 diarization 同源，延迟相对可控，但目前模型体积大。
- 策略：
  1. 默认不开启源分离，仅依靠 diarization。
  2. 当识别结果中出现大量“重叠”标记时，再触发分离流程。
  3. 分离后的音轨按说话人再次送入 Whisper，可显著提升准确率，但延迟翻倍以上。
- MVP 中保留扩展点：`PostProcessingConfig` 可新增 `enable_source_separation`，统一在 `MeetingPipeline` 中调度。
