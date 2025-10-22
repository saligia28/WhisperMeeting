"""Central configuration management for WhisperMeeting."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field


class HardwareConfig(BaseModel):
    target_model: Literal["tiny", "base", "small", "medium", "large-v2", "large-v3"] = "large-v3"
    prefer_gpu: bool = True
    prefer_metal: bool = True
    real_time_latency_budget_ms: int = 2000


class TranscriptionConfig(BaseModel):
    model_size: str = "./models/large-v3"  # Local model path
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    compute_type: Literal["int8", "int8_float16", "float16", "bfloat16", "float32"] = "int8"
    beam_size: int = 5
    vad: bool = True
    language: Optional[str] = "zh"  # Default to Chinese for better accuracy (avoids language detection overhead)
    translate_to_english: bool = False
    temperature: float = 0.0
    initial_prompt: Optional[str] = None  # Removed to prevent hallucination when no speech is detected
    force_simplified_chinese: bool = True


class SummariserConfig(BaseModel):
    provider: Literal["stub", "llama_cpp", "transformers"] = "stub"
    model_path: Optional[Path] = None
    max_input_chars: int = Field(4096, ge=512)
    target_format: Literal["markdown", "notion", "jira"] = "markdown"


class PostProcessingConfig(BaseModel):
    enable_speaker_diarization: bool = False
    diarization_model: str = "pyannote/speaker-diarization"
    enable_alignment: bool = True
    enable_keywords: bool = True


class StorageConfig(BaseModel):
    url: str = "sqlite:///./whispermeeting.db"
    audio_dir: Path = Path("./data/audio")
    transcripts_dir: Path = Path("./data/transcripts")
    summaries_dir: Path = Path("./data/summaries")


class ApiConfig(BaseModel):
    enable_recording: bool = True
    chunk_duration_sec: int = 30


class AppConfig(BaseModel):
    hardware: HardwareConfig = HardwareConfig()
    transcription: TranscriptionConfig = TranscriptionConfig()
    summariser: SummariserConfig = SummariserConfig()
    postprocessing: PostProcessingConfig = PostProcessingConfig()
    storage: StorageConfig = StorageConfig()
    api: ApiConfig = ApiConfig()


def load_config() -> AppConfig:
    """
    Load configuration from environment or default values.

    At this stage we keep it simple, but this hook allows swapping in
    dotenv or a config file loader later.
    """

    return AppConfig()
