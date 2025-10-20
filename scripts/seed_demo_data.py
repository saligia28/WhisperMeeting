"""Seed the local SQLite database with demo meeting data."""

from __future__ import annotations

from datetime import timedelta

from whispermeeting.container import build_container
from whispermeeting.pipeline.transcriber import Transcript, TranscriptSegment


def main() -> None:
    container = build_container()
    meeting_id = "demo-meeting"
    container.repository.create_meeting(meeting_id, title="示例联调会议", language="zh")

    segments = [
        TranscriptSegment(start=0, end=12, text="大家好，今天主要讨论 WhisperMeeting 的集成计划。", speaker="主持人"),
        TranscriptSegment(start=12, end=34, text="后端 API 已经跑通，接下来需要前端切换到真实数据。", speaker="后端"),
        TranscriptSegment(start=34, end=55, text="前端这边明天会完成接口对接，并准备一个演示场景。", speaker="前端"),
        TranscriptSegment(start=55, end=78, text="硬件评估脚本也在测试中，本周内给出结果。", speaker="研发"),
        TranscriptSegment(start=78, end=95, text="最后确认一下，周五我们一起走一遍完整流程。", speaker="主持人"),
    ]

    transcript = Transcript(
        segments=segments,
        language="zh",
        duration=timedelta(seconds=95).total_seconds(),
    )

    container.repository.save_transcript(meeting_id, transcript)

    summary_markdown = """# 会议纪要：WhisperMeeting 集成推进

## 摘要
- WhisperMeeting 后端 API 已经部署完成，具备转写、摘要、存储能力
- 前端将在明日切换到真实数据接口，准备演示流程
- 硬件评估脚本正在验证中，本周内提供评估结果

## 行动项
- [后端] 提供前端所需的接口说明和示例请求
- [前端] 切换至真实数据并准备周五的演示用例
- [研发] 完成硬件评估脚本测试并输出报告

## 关键词
- WhisperMeeting 集成
- 前后端联调
- 硬件评估
"""

    container.repository.save_summary(
        meeting_id,
        summary_markdown,
        keywords=["WhisperMeeting", "联调", "硬件评估"],
    )

    print("Seeded demo meeting:", meeting_id)


if __name__ == "__main__":
    main()
