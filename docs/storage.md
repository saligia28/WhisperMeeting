# 存储结构

```
data/
├── audio/          # 原始录音文件
├── transcripts/    # JSON/文本转写输出
└── summaries/      # Markdown 摘要
```

数据库（SQLite）表结构：

- `meeting`：元数据（id, title, language, duration）。
- `transcriptrow`：分段转写数据，含时间戳与说话人。
- `summary`：Markdown 摘要与关键词列表。

`MeetingRepository` 提供统一接口：`save_transcript`、`save_summary`、`list_meetings`、`get_summary`。未来若迁移至 Postgres，仅需替换数据库 URL 并运行迁移。
