# WhisperMeeting

WhisperMeeting 是一个本地优先的会议助理原型，围绕 TODO 中的需求打造，覆盖从音频采集、转写、后处理到摘要与存储的完整流程。所有模块均可单独运行，方便在不同硬件环境下验证性能。

## 主要能力

- FastAPI 后端提供录音、转写、摘要、下载等接口。
- CLI 原型可对单个音频文件执行“片段 → 转写 → 摘要”的串联流程。
- 模块化设计，涵盖音频采集、转写、说话人分离、摘要、存储等组件，便于替换具体实现。
- 提供硬件评估脚本和测试计划，帮助验证目标环境的可行性。

## 快速开始

```bash
pip install -e .
uvicorn whispermeeting.api.app:app --reload
```

启动后可参考 `docs/api.http` 中的示例请求与 API 交互。CLI 原型位于 `whispermeeting/cli.py`。

## 项目结构

```
src/whispermeeting/
├── api/               # FastAPI 接口
├── audio/             # 音频采集与预处理
├── pipeline/          # 转写、摘要与后处理
├── storage/           # 数据持久化
├── llm/               # 本地大模型封装
├── utils/             # 通用工具
└── cli.py             # 命令行原型
```

完整的架构设计、测试策略与前端草图请见 `docs/` 目录。
