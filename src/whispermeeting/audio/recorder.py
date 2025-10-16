"""
Audio recording utilities based on the sounddevice backend.

The recorder writes chunks to disk so that Whisper can process them in near
real time, following best practices for the `faster-whisper` pipeline.
"""

from __future__ import annotations

import queue
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as wav_write


class AudioRecorder:
    """Streams audio data into wave files."""

    def __init__(
        self,
        sample_rate: int = 16_000,
        channels: int = 1,
        dtype: str = "float32",
        chunk_duration_sec: int = 5,
        output_dir: Path | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.chunk_frames = int(sample_rate * chunk_duration_sec)
        self.output_dir = output_dir or Path("./data/audio/live")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._buffer: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _on_audio(self, indata: np.ndarray, frames: int, time, status) -> None:
        if status:
            print(f"[AudioRecorder] Warning: {status}", flush=True)

        self._buffer.put(indata.copy())

    @contextmanager
    def recording_session(self) -> Generator[None, None, None]:
        """Context manager that emits wave files while the block runs."""

        self._stop_event.clear()
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._on_audio,
        ) as stream:
            self._stream = stream
            self._writer_thread = threading.Thread(target=self._write_loop, daemon=True)
            self._writer_thread.start()
            try:
                yield
            finally:
                self.stop()

    def stop(self) -> None:
        """Stop streaming and flush the buffer."""

        self._stop_event.set()
        if self._stream:
            self._stream.close()
            self._stream = None
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2)

    def _write_loop(self) -> None:
        """Write buffered audio data into chunked wave files."""

        chunk = []
        frames_accumulated = 0
        while not self._stop_event.is_set() or not self._buffer.empty():
            try:
                data = self._buffer.get(timeout=0.1)
            except queue.Empty:
                continue

            chunk.append(data)
            frames_accumulated += len(data)

            if frames_accumulated >= self.chunk_frames:
                stacked = np.concatenate(chunk, axis=0)
                filename = self.output_dir / f"{uuid.uuid4().hex}.wav"
                wav_write(filename, self.sample_rate, stacked)
                chunk = []
                frames_accumulated = 0

