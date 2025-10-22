"""WebSocket-based real-time transcription handler.

This module provides WebSocket endpoints for real-time speech-to-text transcription
using PCM audio streams from the browser's AudioContext API.
"""

from __future__ import annotations

import asyncio
import io
import json
import struct
import wave
from pathlib import Path
from typing import TYPE_CHECKING

import webrtcvad
from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from ..container import ServiceContainer


class RealtimeTranscriptionSession:
    """Manages a single WebSocket session for real-time transcription.

    This class handles:
    - Receiving PCM audio chunks via WebSocket
    - Buffering audio data
    - Converting PCM to WAV format
    - Triggering transcription at regular intervals
    - Sending transcription results back to the client
    """

    def __init__(
        self,
        websocket: WebSocket,
        container: ServiceContainer,
        meeting_id: str,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration: float = 5.0,  # Increased to 5s for better context
        vad_aggressiveness: int = 2,  # VAD sensitivity (0-3, higher = more aggressive)
        min_speech_ratio: float = 0.5,  # Minimum speech ratio to trigger transcription
    ):
        self.websocket = websocket
        self.container = container
        self.meeting_id = meeting_id
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration = chunk_duration
        self.vad_aggressiveness = vad_aggressiveness
        self.min_speech_ratio = min_speech_ratio

        # Audio buffer to accumulate PCM samples
        self.audio_buffer: list[bytes] = []
        self.total_samples = 0
        self.samples_per_chunk = int(sample_rate * chunk_duration)

        # VAD for speech detection (helps avoid cutting mid-sentence)
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        self.min_silence_duration = 0.5  # 500ms silence to trigger processing
        self.silence_samples = 0

        # Temporary directory for audio processing
        self.temp_dir = container.config.storage.audio_dir / "realtime"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Offset for continuous transcription
        self.time_offset = 0.0

    async def handle_session(self) -> None:
        """Main session handler that processes incoming audio and sends transcriptions."""
        try:
            await self.websocket.accept()
            await self.websocket.send_json({
                "type": "session_started",
                "meeting_id": self.meeting_id,
                "sample_rate": self.sample_rate,
                "chunk_duration": self.chunk_duration,
                "config": {
                    "vad_aggressiveness": self.vad_aggressiveness,
                    "min_speech_ratio": self.min_speech_ratio,
                },
            })

            print(f"[WebSocket] Session started for meeting {self.meeting_id} with VAD-based segmentation", flush=True)

            awaiting_first_chunk = True

            while True:
                # Receive message from client (can be bytes or text)
                message = await self.websocket.receive()

                # Handle text messages (config)
                if message.get("type") == "websocket.receive" and message.get("text") is not None:
                    if awaiting_first_chunk:
                        try:
                            payload = json.loads(message["text"])
                            if payload.get("type") == "config":
                                await self._apply_config(payload)
                            else:
                                print(f"[WebSocket] Ignored non-config text message: {payload.get('type')}", flush=True)
                        except json.JSONDecodeError:
                            print("[WebSocket] Invalid JSON config payload, ignoring", flush=True)
                    else:
                        print("[WebSocket] Ignored config (session already started)", flush=True)
                    continue

                # Handle binary messages (audio data)
                if message.get("type") == "websocket.receive" and message.get("bytes") is not None:
                    data = message["bytes"]
                    awaiting_first_chunk = False

                    # Add to buffer
                    self.audio_buffer.append(data)
                    self.total_samples += len(data) // 2  # 16-bit samples = 2 bytes each

                    # Check if we should process based on VAD
                    should_process = await self._should_process_buffer(data)

                    if should_process:
                        await self._process_buffer()
                    continue

                # Handle disconnect
                if message.get("type") == "websocket.disconnect":
                    break

        except WebSocketDisconnect:
            print(f"[WebSocket] Client disconnected from meeting {self.meeting_id}", flush=True)
            # Process any remaining audio
            if self.audio_buffer:
                await self._process_buffer()
        except Exception as exc:
            print(f"[WebSocket] Error in session {self.meeting_id}: {exc}", flush=True)
            await self.websocket.send_json({
                "type": "error",
                "message": str(exc),
            })

    async def _apply_config(self, payload: dict) -> None:
        """Apply configuration from client.

        Args:
            payload: JSON payload with vad_aggressiveness and min_speech_ratio
        """
        try:
            # Validate and apply vad_aggressiveness
            aggressiveness = int(payload.get("vad_aggressiveness", self.vad_aggressiveness))
            self.vad_aggressiveness = max(0, min(3, aggressiveness))

            # Validate and apply min_speech_ratio
            speech_ratio = float(payload.get("min_speech_ratio", self.min_speech_ratio))
            self.min_speech_ratio = max(0.3, min(0.8, speech_ratio))

            # Re-create VAD with new aggressiveness
            self.vad = webrtcvad.Vad(self.vad_aggressiveness)

            print(
                f"[WebSocket] Applied config: vad_aggressiveness={self.vad_aggressiveness}, "
                f"min_speech_ratio={self.min_speech_ratio:.2f}",
                flush=True
            )

            # Send acknowledgment
            await self.websocket.send_json({
                "type": "config_applied",
                "config": {
                    "vad_aggressiveness": self.vad_aggressiveness,
                    "min_speech_ratio": self.min_speech_ratio,
                },
            })
        except Exception as exc:
            print(f"[WebSocket] Failed to apply config: {exc}", flush=True)

    async def _should_process_buffer(self, latest_data: bytes) -> bool:
        """Determine if buffer should be processed based on VAD and duration.

        Args:
            latest_data: Most recent PCM chunk received

        Returns:
            True if buffer should be processed (reached duration threshold + detected silence)
        """
        # Always wait for minimum duration
        if self.total_samples < self.samples_per_chunk:
            return False

        # Use VAD to detect speech activity in latest chunk
        # WebRTC VAD requires frames of specific duration (10, 20, or 30ms)
        # We'll use 30ms frames at 16kHz = 480 samples = 960 bytes
        frame_duration_ms = 30
        frame_size = int(self.sample_rate * frame_duration_ms / 1000) * 2  # 960 bytes for 16kHz

        try:
            # Check last frame for speech activity
            if len(latest_data) >= frame_size:
                frame = latest_data[-frame_size:]
                is_speech = self.vad.is_speech(frame, self.sample_rate)

                if not is_speech:
                    # Accumulate silence duration
                    self.silence_samples += len(latest_data) // 2
                    silence_duration = self.silence_samples / self.sample_rate

                    # If we've accumulated enough silence, process the buffer
                    if silence_duration >= self.min_silence_duration:
                        self.silence_samples = 0  # Reset silence counter
                        print(f"[WebSocket] VAD detected {silence_duration:.2f}s silence, processing buffer", flush=True)
                        return True
                else:
                    # Reset silence counter when speech detected
                    self.silence_samples = 0
        except Exception as vad_error:
            # If VAD fails, fall back to time-based processing
            print(f"[WebSocket] VAD error: {vad_error}, using time-based fallback", flush=True)
            return True

        # Don't let buffer grow indefinitely - process if we've exceeded 2x target duration
        max_samples = self.samples_per_chunk * 2
        if self.total_samples >= max_samples:
            print(f"[WebSocket] Buffer exceeded max duration, forcing processing", flush=True)
            self.silence_samples = 0
            return True

        return False

    def _calculate_speech_ratio(self, pcm_data: bytes) -> float:
        """Calculate the ratio of speech frames to total frames using VAD.

        Args:
            pcm_data: Raw PCM audio bytes

        Returns:
            Ratio of speech frames (0.0 to 1.0)
        """
        # Use 30ms frames for VAD (same as in _should_process_buffer)
        frame_duration_ms = 30
        frame_size = int(self.sample_rate * frame_duration_ms / 1000) * 2  # 960 bytes for 16kHz

        total_frames = 0
        speech_frames = 0

        # Process audio in frames
        for i in range(0, len(pcm_data) - frame_size + 1, frame_size):
            frame = pcm_data[i:i + frame_size]

            # Skip incomplete frames
            if len(frame) < frame_size:
                continue

            total_frames += 1

            try:
                is_speech = self.vad.is_speech(frame, self.sample_rate)
                if is_speech:
                    speech_frames += 1
            except Exception as e:
                # If VAD fails for this frame, skip it
                print(f"[WebSocket] VAD error on frame {i}: {e}", flush=True)
                continue

        # Return ratio (avoid division by zero)
        if total_frames == 0:
            return 0.0

        ratio = speech_frames / total_frames
        return ratio

    async def _process_buffer(self) -> None:
        """Process accumulated audio buffer and send transcription."""
        if not self.audio_buffer:
            return

        try:
            # Combine all buffered PCM data
            pcm_data = b''.join(self.audio_buffer)

            # Calculate actual duration
            duration = len(pcm_data) / 2 / self.sample_rate

            # Check if buffer contains enough speech using VAD
            speech_ratio = self._calculate_speech_ratio(pcm_data)

            # Use instance variable for speech ratio threshold (configurable)
            if speech_ratio < self.min_speech_ratio:
                print(
                    f"[WebSocket] Skipping transcription - speech ratio {speech_ratio:.2%} "
                    f"below threshold {self.min_speech_ratio:.2%}",
                    flush=True
                )

                # Update offset even though we're skipping
                self.time_offset += duration

                # Clear buffer
                self.audio_buffer.clear()
                self.total_samples = 0
                return

            print(f"[WebSocket] Processing buffer - speech ratio: {speech_ratio:.2%}", flush=True)

            # Convert PCM to WAV
            wav_path = self._pcm_to_wav(pcm_data)

            # Run transcription in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(
                None,
                self.container.transcriber.transcribe,
                wav_path
            )

            # Prepare segments with time offset
            segments = [
                {
                    "start": seg.start + self.time_offset,
                    "end": seg.end + self.time_offset,
                    "text": seg.text,
                    "speaker": seg.speaker,
                }
                for seg in transcript.segments
            ]

            # Send transcription result
            await self.websocket.send_json({
                "type": "transcription",
                "segments": segments,
                "offset": self.time_offset,
                "duration": duration,
            })

            print(f"[WebSocket] Sent transcription for {duration:.2f}s audio (offset: {self.time_offset:.2f}s)", flush=True)

            # Update offset for next chunk
            self.time_offset += duration

            # Clear buffer
            self.audio_buffer.clear()
            self.total_samples = 0

            # Cleanup temporary file
            if wav_path.exists():
                wav_path.unlink()

        except Exception as exc:
            print(f"[WebSocket] Transcription error: {exc}", flush=True)
            await self.websocket.send_json({
                "type": "error",
                "message": f"Transcription failed: {exc}",
            })

    def _pcm_to_wav(self, pcm_data: bytes) -> Path:
        """Convert raw PCM data to WAV file format.

        Args:
            pcm_data: Raw PCM audio bytes (16-bit signed integers, little-endian)

        Returns:
            Path to the created WAV file
        """
        wav_path = self.temp_dir / f"{self.meeting_id}_{self.time_offset:.2f}.wav"

        with wave.open(str(wav_path), 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)  # 16-bit = 2 bytes
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_data)

        return wav_path


async def handle_realtime_transcription(
    websocket: WebSocket,
    meeting_id: str,
    container: ServiceContainer,
    sample_rate: int = 16000,
) -> None:
    """WebSocket endpoint handler for real-time transcription.

    Args:
        websocket: FastAPI WebSocket connection
        meeting_id: Unique meeting identifier
        container: Service container with transcriber
        sample_rate: Audio sample rate in Hz (default: 16000)
    """
    # Ensure meeting exists
    container.repository.create_meeting(meeting_id)

    # Create and run session
    session = RealtimeTranscriptionSession(
        websocket=websocket,
        container=container,
        meeting_id=meeting_id,
        sample_rate=sample_rate,
    )

    await session.handle_session()
