# 硬件评估

- `scripts/evaluate_hardware.py` 会打印 CPU、内存、GPU 及推荐模型。
- 默认参数尝试在 Apple Silicon 上启用 Metal，若检测失败会回退至 CPU。
- 建议验证流程：
  1. `python scripts/evaluate_hardware.py`
  2. 根据输出决定是否启用 `medium` 或 `large-v2` 模型。
  3. 通过 `time python -m whispermeeting.cli sample.wav` 测试实时性。
- 若显存不足，可将 `TranscriptionConfig.compute_type` 改为 `int8`，并在 CLI 中观察延迟。
