"""
Dependency wiring for WhisperMeeting.

This keeps module coupling low and makes it easy to orchestrate
mocked services during testing.
"""

from dataclasses import dataclass
from typing import Optional

from .config import AppConfig, load_config
from .llm.summarizer import LocalLLMSummariser
from .pipeline.postprocessing import PostProcessor
from .pipeline.service import MeetingPipeline
from .pipeline.transcriber import FasterWhisperTranscriber
from .storage.repository import MeetingRepository
from .utils.hardware import HardwareProfiler


@dataclass
class ServiceContainer:
    config: AppConfig
    hardware_profiler: HardwareProfiler
    transcriber: FasterWhisperTranscriber
    summariser: LocalLLMSummariser
    post_processor: PostProcessor
    repository: MeetingRepository
    pipeline: MeetingPipeline


def build_container(config: Optional[AppConfig] = None) -> ServiceContainer:
    cfg = config or load_config()
    hardware_profiler = HardwareProfiler(cfg.hardware)
    repository = MeetingRepository(cfg.storage)
    transcriber = FasterWhisperTranscriber(cfg.transcription)
    summariser = LocalLLMSummariser(cfg.summariser)
    post_processor = PostProcessor(cfg.postprocessing, repository)
    pipeline = MeetingPipeline(transcriber, post_processor, summariser, repository)

    return ServiceContainer(
        config=cfg,
        hardware_profiler=hardware_profiler,
        transcriber=transcriber,
        summariser=summariser,
        post_processor=post_processor,
        repository=repository,
        pipeline=pipeline,
    )
