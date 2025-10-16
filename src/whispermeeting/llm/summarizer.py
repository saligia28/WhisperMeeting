"""Summarisation helpers built around local-friendly models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from llama_cpp import Llama
except ImportError:  # pragma: no cover - optional dependency
    Llama = None  # type: ignore

from transformers import pipeline  # type: ignore

from ..config import SummariserConfig
from ..pipeline.transcriber import Transcript


@dataclass
class SummaryResult:
    summary: str
    highlights: list[str]
    action_items: list[str]


class LocalLLMSummariser:
    """Produces structured meeting summaries given a transcript."""

    def __init__(self, config: SummariserConfig) -> None:
        self.cfg = config
        self._llama: Optional[Llama] = None
        self._hf_pipeline = None

        if config.provider == "llama_cpp":
            if Llama is None:
                raise RuntimeError(
                    "llama_cpp is not installed; install `llama-cpp-python` to use this provider."
                )
            if not config.model_path:
                raise ValueError("SummariserConfig.model_path is required for llama_cpp provider.")
            self._llama = Llama(model_path=str(config.model_path), n_ctx=config.max_input_chars)
        else:
            self._hf_pipeline = pipeline(
                "summarization",
                model="facebook/bart-large-cnn",
                device_map="auto",
            )

    def predict(self, transcript: Transcript) -> SummaryResult:
        prompt = self._build_prompt(transcript)

        if self.cfg.provider == "llama_cpp":
            assert self._llama is not None
            output = self._llama(
                prompt,
                max_tokens=1024,
                stop=["</summary>"],
                temperature=0.2,
            )
            raw_text = output["choices"][0]["text"]
        else:
            assert self._hf_pipeline is not None
            compressed = self._hf_pipeline(prompt, max_length=256, min_length=128, do_sample=False)
            raw_text = compressed[0]["summary_text"]

        return self._parse_summary(raw_text)

    def _build_prompt(self, transcript: Transcript) -> str:
        flattened = "\n".join(
            f"[{seg.start:.02f}-{seg.end:.02f}] {seg.speaker or 'Speaker'}: {seg.text}"
            for seg in transcript.segments
        )
        template = (
            "You are a meeting assistant. Summarise the transcript into JSON with keys "
            "`summary`, `highlights`, `action_items`. "
            f"Return only JSON, no prose. Transcript:\n{flattened}\nJSON:"
        )
        if len(template) > self.cfg.max_input_chars:
            template = template[: self.cfg.max_input_chars]
        return template

    def _parse_summary(self, raw_text: str) -> SummaryResult:
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            data = {"summary": raw_text, "highlights": [], "action_items": []}

        return SummaryResult(
            summary=data.get("summary", ""),
            highlights=list(map(str, data.get("highlights", []))),
            action_items=list(map(str, data.get("action_items", []))),
        )
