"""Collect quick hardware metrics to evaluate Whisper feasibility."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from typing import Dict

import psutil

from ..config import HardwareConfig


@dataclass
class HardwareProfile:
    cpu_model: str
    cpu_cores: int
    memory_gb: float
    gpu_name: str | None
    supports_mps: bool
    recommendations: str


class HardwareProfiler:
    """Gathers host metrics and emits simple guidance for Whisper sizing."""

    def __init__(self, config: HardwareConfig) -> None:
        self.cfg = config

    def profile(self) -> HardwareProfile:
        cpu_freq = psutil.cpu_freq()
        cpu_model = platform.processor() or platform.machine()
        memory = psutil.virtual_memory().total / (1024**3)
        gpu_name = self._detect_gpu()
        supports_mps = platform.system() == "Darwin"

        recommendations = self._make_recommendation(memory, gpu_name, supports_mps)

        return HardwareProfile(
            cpu_model=f"{cpu_model} @{cpu_freq.current/1000:.2f}GHz" if cpu_freq else cpu_model,
            cpu_cores=psutil.cpu_count(logical=False) or psutil.cpu_count(),
            memory_gb=memory,
            gpu_name=gpu_name,
            supports_mps=supports_mps,
            recommendations=recommendations,
        )

    def _detect_gpu(self) -> str | None:
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.split("\n")[10].strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

        return None

    def _make_recommendation(self, memory_gb: float, gpu_name: str | None, supports_mps: bool) -> str:
        model = self.cfg.target_model
        notes = []
        if memory_gb < 16:
            notes.append("内存低于16GB，建议使用 small 模型或降低 batch。")
        else:
            notes.append(f"可尝试 {model} 模型，预计每分钟音频占用约 {memory_gb/2:.1f} GB RAM。")

        if gpu_name:
            notes.append(f"检测到 GPU: {gpu_name}。可使用 GPU 加速 Whisper。")
        elif supports_mps and self.cfg.prefer_metal:
            notes.append("使用 Metal 后端可在 Apple Silicon 上获得更好性能。")
        else:
            notes.append("未检测到 GPU，建议开启多线程 CPU 推理。")

        return " ".join(notes)

    def to_dict(self) -> Dict[str, str | int | float | bool]:
        profile = self.profile()
        return {
            "cpu_model": profile.cpu_model,
            "cpu_cores": profile.cpu_cores,
            "memory_gb": round(profile.memory_gb, 2),
            "gpu_name": profile.gpu_name,
            "supports_mps": profile.supports_mps,
            "recommendations": profile.recommendations,
        }
