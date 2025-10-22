#!/usr/bin/env python3
"""Quick test script to verify WebSocket endpoint is accessible."""

import asyncio
import websockets
import json

async def test_websocket():
    """Test WebSocket connection to realtime transcription endpoint."""
    uri = "ws://localhost:8002/meetings/test_meeting/transcribe/realtime"

    try:
        print(f"Attempting to connect to: {uri}")
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connection established!")

            # Wait for session_started message
            message = await websocket.recv()
            data = json.loads(message)
            print(f"✅ Received session_started message: {data}")

            # Send a small PCM sample (silence - all zeros)
            # 16-bit PCM, 16000 Hz, 0.1 seconds = 1600 samples = 3200 bytes
            silence = b'\x00' * 3200
            await websocket.send(silence)
            print("✅ Sent PCM data successfully")

            # Wait a bit for response (won't get transcription for silence, but shouldn't error)
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"Received response: {response}")
            except asyncio.TimeoutError:
                print("⏱️  No immediate response (expected for short silence)")

            print("\n✅ WebSocket endpoint is working correctly!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket())
