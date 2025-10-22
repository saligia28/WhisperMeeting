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

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, WebSocket, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..container import ServiceContainer, build_container
from .realtime import handle_realtime_transcription


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


def get_user_id(request: Request) -> str:
    """Extract user identifier from request (using client IP as temporary solution)."""
    # Use X-Forwarded-For if behind proxy, otherwise use direct client IP
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    return f"user_{client_ip}"


UserIdDep = Annotated[str, Depends(get_user_id)]


class MeetingCreateRequest(BaseModel):
    meeting_id: str | None = None
    title: str | None = None
    language: str | None = None


class MeetingResponse(BaseModel):
    id: str
    title: str | None = None
    language: str | None = None
    duration: float | None = None


class UserSettingsResponse(BaseModel):
    """User settings for VAD parameters."""
    vad_aggressiveness: int
    min_speech_ratio: float


class UserSettingsUpdateRequest(BaseModel):
    """Request model for updating user settings."""
    vad_aggressiveness: int | None = None
    min_speech_ratio: float | None = None


def _run_transcription_pipeline(
    meeting_id: str,
    wav_path: Path,
    container: ServiceContainer,
    tasks_dict: dict[str, TaskInfo],
    user_id: str,
) -> None:
    """后台任务：执行转写和摘要流程"""
    task = tasks_dict[meeting_id]
    try:
        # 更新状态为处理中
        task.status = TaskStatus.PROCESSING
        task.progress = 0.1
        task.updated_at = datetime.now()

        # 获取用户VAD设置
        user_settings = container.repository.get_user_settings(user_id)
        print(
            f"[Background] Using user settings for {user_id}: "
            f"vad_aggressiveness={user_settings.vad_aggressiveness}, "
            f"min_speech_ratio={user_settings.min_speech_ratio}",
            flush=True
        )

        # 执行转写流程(应用用户设置)
        output = container.pipeline.run(
            meeting_id,
            wav_path,
            vad_aggressiveness=user_settings.vad_aggressiveness,
            min_speech_ratio=user_settings.min_speech_ratio,
        )

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

    # 记录上传文件的详细信息
    print(f"[Upload] 文件: {upload.filename}, 大小: {len(data)} 字节, MIME: {upload.content_type}", flush=True)

    # 验证音频文件格式（仅作为警告，不阻止处理）
    if suffix.lower() == ".webm":
        # WebM 文件应该以 0x1A 0x45 0xDF 0xA3 (EBML 头) 开始
        if len(data) >= 4:
            header = data[:4]
            if header == b'\x1a\x45\xdf\xa3':
                print(f"[Upload] WebM 文件头验证成功（完整文件）", flush=True)
            else:
                print(f"[Upload] 警告：WebM 文件头不标准: {header.hex()}", flush=True)
                print(f"[Upload] 这可能是 MediaRecorder 分块流（缺少完整头部），将尝试转换", flush=True)
    elif suffix.lower() == ".mp4":
        # MP4 文件通常以 ftyp 开始（偏移 4 字节后）
        if len(data) >= 12:
            ftype_marker = data[4:8]
            if ftype_marker == b'ftyp':
                print(f"[Upload] MP4 文件头验证成功", flush=True)
            else:
                print(f"[Upload] 警告：MP4 文件头不标准。标记: {ftype_marker}", flush=True)

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
    # WebM/Opus 音频转换参数（针对浏览器 MediaRecorder 生成的文件）
    # -hide_banner: 隐藏FFmpeg版本信息
    # -loglevel error: 只显示错误日志
    # -strict -2: 允许实验性编解码器
    # -vn: 忽略视频流（WebM 可能包含元数据视频轨道）
    # -acodec libopus: 显式指定 Opus 解码器（WebM 常用）
    # -f wav: 强制输出WAV格式
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(source),
        "-vn",            # 忽略视频流
        "-ar", "16000",   # 16kHz sample rate
        "-ac", "1",       # Mono
        "-strict", "-2",  # Allow experimental codecs
        "-f", "wav",      # Force WAV output
        str(target)
    ]

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
        print(f"[FFmpeg] File size: {source.stat().st_size} bytes", flush=True)
        if stdout:
            print(f"[FFmpeg] stdout: {stdout}", flush=True)
        if stderr:
            print(f"[FFmpeg] stderr: {stderr}", flush=True)

        # 检查文件是否为空
        file_size = source.stat().st_size
        if file_size == 0:
            detail = f"上传的音频文件为空（0 字节）。请检查前端录音逻辑。"
        elif file_size < 100:
            detail = f"上传的音频文件过小（{file_size} 字节），可能未正确录制。"
        elif "Invalid data" in stderr or "does not contain any stream" in stderr:
            detail = f"音频转换失败：上传的 {source.suffix} 文件可能已损坏或格式不受支持。文件大小：{file_size} 字节"
        elif "moov atom not found" in stderr:
            detail = f"音频转换失败：{source.suffix} 文件不完整（moov atom 缺失）。这通常表示录音未正常完成。"
        else:
            detail = f"音频转换失败 ({source.suffix} -> WAV)。"
            if stderr:
                detail += f" FFmpeg 错误：{stderr[-200:]}"

        raise HTTPException(status_code=500, detail=detail) from exc

    return target


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.get("/hardware/profile")
def hardware_profile(container: ContainerDep) -> dict:
    return container.hardware_profiler.to_dict()


@api.get("/user/settings", response_model=UserSettingsResponse)
def get_user_settings(user_id: UserIdDep, container: ContainerDep) -> UserSettingsResponse:
    """Get current user's VAD settings."""
    settings = container.repository.get_user_settings(user_id)
    return UserSettingsResponse(
        vad_aggressiveness=settings.vad_aggressiveness,
        min_speech_ratio=settings.min_speech_ratio,
    )


@api.put("/user/settings", response_model=UserSettingsResponse)
def update_user_settings(
    payload: UserSettingsUpdateRequest,
    user_id: UserIdDep,
    container: ContainerDep,
) -> UserSettingsResponse:
    """Update user's VAD settings."""
    settings = container.repository.update_user_settings(
        user_id=user_id,
        vad_aggressiveness=payload.vad_aggressiveness,
        min_speech_ratio=payload.min_speech_ratio,
    )
    return UserSettingsResponse(
        vad_aggressiveness=settings.vad_aggressiveness,
        min_speech_ratio=settings.min_speech_ratio,
    )


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
    user_id: UserIdDep,
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

    # 启动后台任务(传递user_id以应用用户VAD设置)
    background_tasks.add_task(
        _run_transcription_pipeline,
        meeting_id,
        wav_path,
        container,
        request.app.state.tasks,
        user_id,
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


@api.websocket("/meetings/{meeting_id}/transcribe/realtime")
async def websocket_realtime_transcription(
    websocket: WebSocket,
    meeting_id: str,
    sample_rate: int = 16000,
) -> None:
    """WebSocket endpoint for real-time transcription using PCM audio streams.

    The client should send raw PCM audio data (16-bit signed integers, little-endian)
    at the specified sample rate. Transcription results are sent back as JSON messages.

    Message format (server to client):
    - session_started: {"type": "session_started", "meeting_id": str, ...}
    - transcription: {"type": "transcription", "segments": [...], "offset": float, ...}
    - error: {"type": "error", "message": str}
    """
    # Get container from app state instead of dependency injection
    container = websocket.app.state.container
    await handle_realtime_transcription(websocket, meeting_id, container, sample_rate)
