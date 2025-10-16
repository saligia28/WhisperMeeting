from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from whispermeeting.api.app import api, get_container
from whispermeeting.config import StorageConfig
from whispermeeting.pipeline.service import PipelineOutput
from whispermeeting.pipeline.transcriber import Transcript, TranscriptSegment


class FakeHardwareProfiler:
    def to_dict(self):
        return {"cpu_model": "Test CPU", "cpu_cores": 8, "memory_gb": 32}


class FakeRepository:
    def __init__(self):
        self._meetings = []

    def record(self, meeting_id, transcript):
        self._meetings.append(
            SimpleNamespace(
                id=meeting_id,
                language=transcript.language,
                duration=transcript.duration,
                title=None,
            )
        )

    def list_meetings(self):
        return self._meetings


class FakePipeline:
    def __init__(self, storage_cfg: StorageConfig, repo: FakeRepository):
        self.storage_cfg = storage_cfg
        self.repo = repo

    def run(self, meeting_id, audio_path):
        transcript = Transcript(
            segments=[TranscriptSegment(start=0.0, end=1.0, text="Hello", speaker="Alice")],
            language="en",
            duration=1.0,
        )
        self.repo.record(meeting_id, transcript)

        summary_path = self.storage_cfg.summaries_dir / f"{meeting_id}.md"
        summary_path.write_text("# Summary", encoding="utf-8")

        return PipelineOutput(
            meeting_id=meeting_id,
            transcript=transcript,
            summary_markdown="# Summary",
            keywords=["Hello"],
            highlights=["Greeting"],
            action_items=["None"],
        )


class FakeContainer:
    def __init__(self, tmp_path):
        self.config = SimpleNamespace(
            storage=StorageConfig(
                url=f"sqlite:///{tmp_path / 'api.db'}",
                audio_dir=tmp_path / "audio",
                transcripts_dir=tmp_path / "transcripts",
                summaries_dir=tmp_path / "summaries",
            )
        )
        self.config.storage.audio_dir.mkdir(parents=True, exist_ok=True)
        self.config.storage.summaries_dir.mkdir(parents=True, exist_ok=True)

        self.hardware_profiler = FakeHardwareProfiler()
        self.repository = FakeRepository()
        self.pipeline = FakePipeline(self.config.storage, self.repository)


def test_api_transcribe_and_list(tmp_path, monkeypatch):
    container = FakeContainer(tmp_path)

    api.dependency_overrides[get_container] = lambda: container
    client = TestClient(api)

    files = {"audio": ("sample.wav", b"fake-audio", "audio/wav")}
    meeting_id = uuid4().hex
    response = client.post(f"/meetings/{meeting_id}/transcribe", files=files)
    assert response.status_code == 200
    assert response.json()["meeting_id"] == meeting_id

    list_resp = client.get("/meetings")
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["meeting_id"] == meeting_id

    hardware_resp = client.get("/hardware/profile")
    assert hardware_resp.json()["cpu_model"] == "Test CPU"

    summary_resp = client.get(f"/meetings/{meeting_id}/summary")
    assert summary_resp.status_code == 200

    api.dependency_overrides.clear()
