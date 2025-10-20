"""FastAPI app providing meeting assistant endpoints."""

from __future__ import annotations

import shutil
import subprocess
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..container import ServiceContainer, build_container


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskInfo(BaseModel):
    """任务状态信息"""
    meeting_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    progress: float = 0.0  # 0.0 - 1.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - initialize resources on startup, cleanup on shutdown."""
    # Startup: create ServiceContainer once and share across all requests
    print("[WhisperMeeting] Initializing ServiceContainer...", flush=True)
    container = build_container()
    app.state.container = container

    # 初始化任务状态追踪字典
    app.state.tasks = {}
    print("[WhisperMeeting] ServiceContainer initialized successfully.", flush=True)

    yield

    # Shutdown: cleanup if needed
    print("[WhisperMeeting] Shutting down...", flush=True)


api = FastAPI(title="WhisperMeeting API", version="0.1.0", lifespan=lifespan)
app = api  # uvicorn entrypoint

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_container(request: Request) -> ServiceContainer:
    """Get the shared ServiceContainer instance from app state."""
    return request.app.state.container


ContainerDep = Annotated[ServiceContainer, Depends(get_container)]


class MeetingCreateRequest(BaseModel):
    meeting_id: str | None = None
    title: str | None = None
    language: str | None = None


class MeetingResponse(BaseModel):
    id: str
    title: str | None = None
    language: str | None = None
    duration: float | None = None


def _run_transcription_pipeline(
    meeting_id: str,
    wav_path: Path,
    container: ServiceContainer,
    tasks_dict: dict[str, TaskInfo],
) -> None:
    """后台任务：执行转写和摘要流程"""
    task = tasks_dict[meeting_id]
    try:
        # 更新状态为处理中
        task.status = TaskStatus.PROCESSING
        task.progress = 0.1
        task.updated_at = datetime.now()

        # 执行转写流程
        output = container.pipeline.run(meeting_id, wav_path)

        # 完成
        task.status = TaskStatus.COMPLETED
        task.progress = 1.0
        task.updated_at = datetime.now()

        print(f"[Background] Meeting {meeting_id} transcription completed.", flush=True)

    except Exception as exc:
        # 记录错误
        task.status = TaskStatus.FAILED
        task.error = f"{type(exc).__name__}: {str(exc)}"
        task.updated_at = datetime.now()
        print(f"[Background] Meeting {meeting_id} failed: {task.error}", flush=True)
        print(traceback.format_exc(), flush=True)

    finally:
        # 清理临时文件
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)


async def _write_upload(upload: UploadFile, base_dir: Path) -> Path:
    suffix = Path(upload.filename or "").suffix or ".bin"
    target = base_dir / f"{uuid.uuid4().hex}{suffix}"
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传的音频文件为空。")
    target.write_bytes(data)
    return target


def _ensure_wav(source: Path) -> Path:
    """Convert audio file to WAV format required by Whisper.

    Args:
        source: Path to source audio file

    Returns:
        Path to WAV file (16kHz mono)

    Raises:
        HTTPException: If FFmpeg is not available or conversion fails
    """
    if source.suffix.lower() == ".wav":
        return source

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise HTTPException(status_code=500, detail="缺少 ffmpeg，无法转换音频。请安装后重试。")

    target = source.with_suffix(".wav")
    cmd = [ffmpeg_bin, "-y", "-i", str(source), "-ar", "16000", "-ac", "1", str(target)]

    print(f"[FFmpeg] Converting {source.name} to WAV...", flush=True)

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"[FFmpeg] Conversion successful: {target.name}", flush=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        stdout = exc.stdout.strip() if exc.stdout else ""
        print(f"[FFmpeg] Conversion failed for {source.name}", flush=True)
        print(f"[FFmpeg] Command: {' '.join(cmd)}", flush=True)
        print(f"[FFmpeg] Exit code: {exc.returncode}", flush=True)
        if stdout:
            print(f"[FFmpeg] stdout: {stdout}", flush=True)
        if stderr:
            print(f"[FFmpeg] stderr: {stderr}", flush=True)

        detail = f"音频转换失败 ({source.suffix} -> WAV)：Whisper 只支持 WAV 格式。"
        if "Invalid data" in stderr or "does not contain any stream" in stderr:
            detail += " 上传的音频文件可能已损坏或格式不受支持。"
        elif stderr:
            detail += f" FFmpeg 错误：{stderr[-200:]}"  # 只显示最后 200 字符

        raise HTTPException(status_code=500, detail=detail) from exc

    return target


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.get("/hardware/profile")
def hardware_profile(container: ContainerDep) -> dict:
    return container.hardware_profiler.to_dict()


@api.post("/meetings", response_model=MeetingResponse)
def create_meeting(payload: MeetingCreateRequest, container: ContainerDep) -> MeetingResponse:
    meeting_id = payload.meeting_id or uuid.uuid4().hex
    meeting = container.repository.create_meeting(meeting_id, title=payload.title, language=payload.language)
    return MeetingResponse(id=meeting.id, title=meeting.title, language=meeting.language, duration=meeting.duration)


@api.post("/meetings/{meeting_id}/transcribe/chunk")
async def transcribe_chunk(
    meeting_id: str,
    container: ContainerDep,
    audio: UploadFile = File(...),
    offset: float = 0.0,
):
    upload_dir = container.config.storage.audio_dir / "chunks"
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = await _write_upload(audio, upload_dir)
    wav_path = None
    converted_file = False

    try:
        # 转换为 WAV 格式（Whisper 必需）
        wav_path = _ensure_wav(temp_path)
        converted_file = wav_path != temp_path

        # 执行转写
        container.repository.create_meeting(meeting_id)
        transcript = container.transcriber.transcribe(wav_path)
    except HTTPException:
        # FFmpeg 转换失败，直接向用户报错
        raise
    except Exception as exc:  # pragma: no cover - runtime protection
        raise HTTPException(status_code=500, detail=f"实时转写失败：{exc}") from exc
    finally:
        # 清理临时文件
        if converted_file and wav_path and wav_path.exists():
            wav_path.unlink(missing_ok=True)
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    segments = [
        {
            "start": seg.start + offset,
            "end": seg.end + offset,
            "text": seg.text,
            "speaker": seg.speaker,
        }
        for seg in transcript.segments
    ]

    return {"meeting_id": meeting_id, "segments": segments}


@api.post("/meetings/{meeting_id}/transcribe")
async def transcribe_meeting(
    meeting_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    container: ContainerDep,
    audio: UploadFile = File(...),
) -> dict:
    """启动异步转写任务，立即返回任务状态"""
    upload_dir = container.config.storage.audio_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = await _write_upload(audio, upload_dir)
    wav_path = _ensure_wav(temp_path)

    # 创建任务状态记录
    now = datetime.now()
    task_info = TaskInfo(
        meeting_id=meeting_id,
        status=TaskStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    request.app.state.tasks[meeting_id] = task_info

    # 启动后台任务
    background_tasks.add_task(
        _run_transcription_pipeline,
        meeting_id,
        wav_path,
        container,
        request.app.state.tasks,
    )

    return {
        "meeting_id": meeting_id,
        "status": task_info.status,
        "message": "转写任务已启动，请使用 GET /meetings/{meeting_id}/status 查询进度",
    }


@api.get("/meetings/{meeting_id}/status")
def get_task_status(meeting_id: str, request: Request) -> TaskInfo:
    """查询转写任务状态"""
    task = request.app.state.tasks.get(meeting_id)
    if not task:
        raise HTTPException(status_code=404, detail="未找到该会议的任务记录")
    return task


@api.get("/meetings/{meeting_id}/result")
def get_transcription_result(meeting_id: str, container: ContainerDep, request: Request) -> dict:
    """获取完成的转写结果（仅在任务完成后可用）"""
    task = request.app.state.tasks.get(meeting_id)
    if not task:
        raise HTTPException(status_code=404, detail="未找到该会议的任务记录")

    if task.status == TaskStatus.PENDING or task.status == TaskStatus.PROCESSING:
        raise HTTPException(status_code=425, detail=f"任务尚未完成，当前状态：{task.status}")

    if task.status == TaskStatus.FAILED:
        raise HTTPException(status_code=500, detail=f"任务执行失败：{task.error}")

    # 从数据库获取结果
    segments = container.repository.get_transcript_segments(meeting_id)
    summary = container.repository.get_summary(meeting_id)

    segment_payload = [
        {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "speaker": seg.speaker,
        }
        for seg in segments
    ]

    return {
        "meeting_id": meeting_id,
        "status": task.status,
        "segments": segment_payload,
        "summary": summary,
    }


@api.get("/meetings")
def list_meetings(container: ContainerDep) -> list[dict]:
    meetings = container.repository.list_meetings()
    return [
        {
            "id": m.id,
            "language": m.language,
            "duration": m.duration,
            "title": m.title,
        }
        for m in meetings
    ]


@api.delete("/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting_id: str, container: ContainerDep) -> Response:
    deleted = container.repository.delete_meeting(meeting_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会议不存在或已删除。")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@api.get("/meetings/{meeting_id}/summary")
def download_summary(meeting_id: str, container: ContainerDep) -> FileResponse:
    summary_path = Path(container.config.storage.summaries_dir) / f"{meeting_id}.md"
    if not summary_path.exists():
        return JSONResponse({"detail": "Summary not found"}, status_code=404)
    return FileResponse(summary_path)


@api.get("/meetings/{meeting_id}/transcript")
def get_transcript(meeting_id: str, container: ContainerDep) -> list[dict]:
    segments = container.repository.get_transcript_segments(meeting_id)
    return [
        {
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
            "speaker": segment.speaker,
        }
        for segment in segments
    ]
