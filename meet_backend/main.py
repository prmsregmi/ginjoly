import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.meet_bot import join_meet

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

connected_clients: list[WebSocket] = []


async def broadcast(message: dict):
    for ws in connected_clients:
        try:
            await ws.send_json(message)
        except Exception:
            pass


class JoinRequest(BaseModel):
    meeting_url: str


@app.post("/api/join")
async def join_meeting(req: JoinRequest):
    asyncio.create_task(run_bot(req.meeting_url))
    return {"status": "joining"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(ws)


async def run_bot(meeting_url: str):
    # Shared queue: meet_bot puts audio in, pipeline reads it out
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def on_status(msg: str):
        print(f"[status] {msg}")
        await broadcast({"type": "status", "message": msg})

    async def on_audio(pcm_bytes: bytes):
        await audio_queue.put(pcm_bytes)

    async def on_transcript(text: str):
        print(f"[transcript] {text}")
        await broadcast({"type": "transcript", "text": text})

    await broadcast({"type": "status", "message": "Starting bot..."})

    # Run meet_bot and pipeline concurrently
    from pipeline_bridge import run_meet_pipeline

    meet_task = asyncio.create_task(join_meet(meeting_url, on_audio, on_status))
    pipeline_task = asyncio.create_task(run_meet_pipeline(audio_queue, on_transcript))

    try:
        await asyncio.gather(meet_task, pipeline_task)
    except Exception as e:
        print(f"[error] {e}")
        await broadcast({"type": "status", "message": f"Error: {e}"})
    finally:
        # Signal pipeline to stop
        await audio_queue.put(None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
