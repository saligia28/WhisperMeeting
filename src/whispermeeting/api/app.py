"""FastAPI app providing meeting assistant endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..container import ServiceContainer, build_container


api = FastAPI(title="WhisperMeeting API", version="0.1.0")


def get_container() -> ServiceContainer:
    return build_container()


ContainerDep = Annotated[ServiceContainer, Depends(get_container)]


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.get("/hardware/profile")
def hardware_profile(container: ContainerDep) -> dict:
    return container.hardware_profiler.to_dict()


@api.post("/meetings/{meeting_id}/transcribe")
async def transcribe_meeting(
    meeting_id: str,
    container: ContainerDep,
    audio: UploadFile = File(...),
) -> dict:
    temp_path = Path(container.config.storage.audio_dir) / f"{uuid.uuid4().hex}-{audio.filename}"
    temp_path.write_bytes(await audio.read())

    output = container.pipeline.run(meeting_id, temp_path)

    return {
        "meeting_id": meeting_id,
        "language": output.transcript.language,
        "keywords": output.keywords,
        "highlights": output.highlights,
        "action_items": output.action_items,
    }


@api.get("/meetings")
def list_meetings(container: ContainerDep) -> list[dict]:
    meetings = container.repository.list_meetings()
    return [
        {
            "meeting_id": m.id,
            "language": m.language,
            "duration": m.duration,
            "title": m.title,
        }
        for m in meetings
    ]


@api.get("/meetings/{meeting_id}/summary")
def download_summary(meeting_id: str, container: ContainerDep) -> FileResponse:
    summary_path = Path(container.config.storage.summaries_dir) / f"{meeting_id}.md"
    if not summary_path.exists():
        return JSONResponse({"detail": "Summary not found"}, status_code=404)
    return FileResponse(summary_path)
