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

from ..config import SummariserConfig
from ..pipeline.transcriber import Transcript

try:
    from transformers import pipeline  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pipeline = None  # type: ignore


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
        self._mode = config.provider

        if config.provider == "stub":
            self._mode = "stub"
        elif config.provider == "llama_cpp":
            if Llama is None:
                raise RuntimeError(
                    "llama_cpp is not installed; install `llama-cpp-python` to use this provider."
                )
            if not config.model_path:
                raise ValueError("SummariserConfig.model_path is required for llama_cpp provider.")
            self._llama = Llama(model_path=str(config.model_path), n_ctx=config.max_input_chars)
        elif config.provider == "transformers":
            if pipeline is None:
                raise RuntimeError(
                    "transformers is not installed; install `transformers` to use this provider."
                )
            self._hf_pipeline = pipeline(
                "summarization",
                model="facebook/bart-large-cnn",
                device_map="auto",
            )
        else:  # pragma: no cover - safety net
            self._mode = "stub"

    def predict(self, transcript: Transcript) -> SummaryResult:
        if self._mode == "stub":
            return self._predict_stub(transcript)

        prompt = self._build_prompt(transcript)

        if self._mode == "llama_cpp":
            assert self._llama is not None
            output = self._llama(
                prompt,
                max_tokens=1024,
                stop=["</summary>"],
                temperature=0.2,
            )
            raw_text = output["choices"][0]["text"]
        elif self._mode == "transformers":
            assert self._hf_pipeline is not None
            compressed = self._hf_pipeline(prompt, max_length=256, min_length=128, do_sample=False)
            raw_text = compressed[0]["summary_text"]
        else:  # fallback
            return self._predict_stub(transcript)

        return self._parse_summary(raw_text)

    def _predict_stub(self, transcript: Transcript) -> SummaryResult:
        """Lightweight fallback that extracts key sentences without external models."""

        if not transcript.segments:
            return SummaryResult(summary="未检测到语音内容。", highlights=[], action_items=[])

        ordered = sorted(transcript.segments, key=lambda seg: seg.start)
        first_lines = [seg.text for seg in ordered[:3]]
        summary = " ".join(first_lines) if first_lines else "会议内容待补充。"

        highlights = []
        for seg in ordered:
            if seg.text:
                highlights.append(seg.text)
            if len(highlights) >= 5:
                break

        action_items = [seg.text for seg in ordered if any(keyword in seg.text for keyword in ("TODO", "待办", "action"))]

        return SummaryResult(
            summary=summary,
            highlights=highlights,
            action_items=action_items[:5],
        )

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
