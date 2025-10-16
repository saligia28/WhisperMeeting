# 需求分析自动化与导出

## 摘要 → 结构化表格
- `LocalLLMSummariser` 输出 JSON（summary/highlights/action_items）。
- 计划新增 `formatters/notion.py`, `formatters/jira.py`，将 JSON 转为目标平台 payload。

## 导出流程
1. CLI 或 API 获取会议 `meeting_id`。
2. 调用 `python -m whispermeeting.export notion --meeting-id <id>`（预留命令），将摘要同步到 Notion 数据库。
3. Jira 导出则写入优先级、负责人及验收标准。

## 自动化钩子
- 可通过 cron/launchd 定时启动录音任务，并在会后自动转写。
- 与日历集成：读取当天会议事件，自动生成 meeting_id 并提前创建会议条目。
- 预留 `webhooks` 触发器，将最终 Markdown 推送到 Slack/企业微信。
