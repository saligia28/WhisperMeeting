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


class FakeTranscriber:
    def transcribe(self, audio_path):
        return Transcript(
            segments=[
                TranscriptSegment(start=0.0, end=1.0, text="Hello", speaker="Alice"),
                TranscriptSegment(start=1.0, end=2.0, text="World", speaker="Bob"),
            ],
            language="en",
            duration=2.0,
        )


class FakeRepository:
    def __init__(self):
        self._meetings = []
        self._segments = []
        self._summaries = {}

    def create_meeting(self, meeting_id, title=None, language=None):
        meeting = SimpleNamespace(
            id=meeting_id,
            language=language,
            duration=None,
            title=title,
        )
        self._meetings.append(meeting)
        return meeting

    def record(self, meeting_id, transcript):
        self._meetings.append(
            SimpleNamespace(
                id=meeting_id,
                language=transcript.language,
                duration=transcript.duration,
                title=None,
            )
        )
        self._segments = transcript.segments

    def list_meetings(self):
        return self._meetings

    def delete_meeting(self, meeting_id):
        before = len(self._meetings)
        self._meetings = [meeting for meeting in self._meetings if meeting.id != meeting_id]
        return len(self._meetings) < before

    def get_transcript_segments(self, meeting_id):
        return self._segments

    def get_summary(self, meeting_id):
        return self._summaries.get(meeting_id)

    def save_summary(self, meeting_id, markdown, keywords):
        self._summaries[meeting_id] = markdown

    def save_transcript(self, meeting_id, transcript):
        self._segments = transcript.segments


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
        self.transcriber = FakeTranscriber()


def test_api_transcribe_and_list(tmp_path, monkeypatch):
    container = FakeContainer(tmp_path)

    # 创建一个不需要 request 参数的 getter
    def mock_get_container():
        return container

    api.dependency_overrides[get_container] = mock_get_container
    with TestClient(api) as client:
        # 确保 app.state.tasks 被初始化（lifespan 中设置）
        # TestClient 会自动运行 lifespan，但为了确保兼容性，我们也可以手动检查
        if not hasattr(client.app.state, "tasks"):
            client.app.state.tasks = {}

        files = {"audio": ("sample.wav", b"fake-audio", "audio/wav")}
        meeting_id = uuid4().hex
        response = client.post(f"/meetings/{meeting_id}/transcribe", files=files)
        assert response.status_code == 200
        assert response.json()["meeting_id"] == meeting_id
        assert response.json()["status"] == "pending"

        # 测试状态查询端点
        status_resp = client.get(f"/meetings/{meeting_id}/status")
        assert status_resp.status_code == 200

        list_resp = client.get("/meetings")
        assert list_resp.status_code == 200

        hardware_resp = client.get("/hardware/profile")
        assert hardware_resp.json()["cpu_model"] == "Test CPU"

    api.dependency_overrides.clear()


def test_api_delete_meeting(tmp_path, monkeypatch):
    container = FakeContainer(tmp_path)
    meeting_id = uuid4().hex
    container.repository.create_meeting(meeting_id)

    def mock_get_container():
        return container

    api.dependency_overrides[get_container] = mock_get_container
    with TestClient(api) as client:
        resp = client.delete(f"/meetings/{meeting_id}")
        assert resp.status_code == 204

        list_resp = client.get("/meetings")
        assert list_resp.json() == []

        missing_resp = client.delete(f"/meetings/{meeting_id}")
        assert missing_resp.status_code == 404

    api.dependency_overrides.clear()
