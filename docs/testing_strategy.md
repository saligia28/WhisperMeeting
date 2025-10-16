# 测试与监控方案

1. **单元测试**
   - `tests/test_pipeline.py`：mock 转写与摘要，验证 `MeetingPipeline` 调用顺序。
   - `tests/test_api.py`：使用 `httpx.AsyncClient` 调用 FastAPI，确保返回结构完整。
   - `tests/test_repository.py`：使用临时 SQLite 检查持久化行为。
2. **集成测试**
   - 准备 1 分钟多说话人样本，跑完整 CLI 流程，验证摘要输出格式和关键词生成。
3. **性能监控**
   - CLI 中记录音频时长与转写耗时，验证是否满足实时/准实时要求。
   - API 增加 `/metrics`（后续）暴露推理队列长度、GPU 利用率。
4. **用户验收**
   - 通过前端草图实现初版界面，邀请用户标注关键点并导出 Markdown，对照手工记录。
   - 监控日志中的 diarization 失败率，必要时回退至固定说话人标签策略。
