"""Command line prototype: audio file -> transcript -> summary."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from . import build_container


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WhisperMeeting CLI prototype")
    parser.add_argument("audio", type=Path, help="Path to the audio file to transcribe")
    parser.add_argument(
        "--meeting-id",
        type=str,
        default=None,
        help="Optional meeting ID; defaults to a random UUID.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.audio.exists():
        raise FileNotFoundError(args.audio)

    container = build_container()
    meeting_id = args.meeting_id or uuid.uuid4().hex

    output = container.pipeline.run(meeting_id, args.audio)

    print(f"[WhisperMeeting] Transcript stored for meeting {meeting_id}")
    print(f"[WhisperMeeting] Summary keywords: {', '.join(output.keywords)}")


if __name__ == "__main__":
    main()
