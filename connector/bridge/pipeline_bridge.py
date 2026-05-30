"""Bridge between the Playwright Meet capture and the ginjoly meeting agent.

`meet_bot.join_meet` captures the meeting's mixed audio as raw 16 kHz mono PCM
and pushes each chunk onto an asyncio.Queue. `MeetTransport` turns that queue
into a pipecat input transport; the meeting agent's pipeline (VAD -> STT ->
WakeNameGate -> brain/MCP -> TTS) runs in-process over it.

Audio injection back into the Meet is deferred, so the output sink drops the
bot's TTS audio for now; the bot's replies surface to the frontend via the
on_assistant callback instead. Swap `NullOutput` for a real Meet audio sink when
injection lands.
"""

import asyncio
import os
import sys

# The ginjoly backend lives in the repo's `server/` package (two levels up from
# connector/bridge/); make `app`/`bot` importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server"))

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    StartFrame,
)
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_transport import BaseTransport


class MeetAudioSource(FrameProcessor):
    """Pumps raw PCM from the Meet queue into the pipeline as InputAudioRawFrames.

    The pump starts when the pipeline's StartFrame arrives (rather than relying
    on a transport start hook) and stops on End/Cancel. A None on the queue means
    the Meet ended, which we translate into an EndFrame to drain the pipeline.
    """

    def __init__(self, queue: asyncio.Queue, sample_rate: int = 16000, **kwargs):
        super().__init__(**kwargs)
        self._queue = queue
        self._sample_rate = sample_rate
        self._pump: asyncio.Task | None = None

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame) and self._pump is None:
            self._pump = asyncio.create_task(self._run())
        elif isinstance(frame, (EndFrame, CancelFrame)) and self._pump:
            self._pump.cancel()

    async def _run(self):
        while True:
            data = await self._queue.get()
            if data is None:
                await self.push_frame(EndFrame())
                break
            await self.push_frame(
                InputAudioRawFrame(
                    audio=data, sample_rate=self._sample_rate, num_channels=1
                )
            )


class NullOutput(FrameProcessor):
    """Drops the bot's TTS audio (injection into Meet is deferred) but forwards
    control frames so the pipeline can start and shut down cleanly."""

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, OutputAudioRawFrame):
            return
        await self.push_frame(frame, direction)


class MeetTransport(BaseTransport):
    """Minimal transport bridging the Meet audio queue into pipecat."""

    def __init__(self, audio_queue: asyncio.Queue, sample_rate: int = 16000, **kwargs):
        super().__init__(**kwargs)
        self._source = MeetAudioSource(audio_queue, sample_rate, name="MeetAudioSource")
        self._sink = NullOutput(name="NullOutput")

    def input(self) -> FrameProcessor:
        return self._source

    def output(self) -> FrameProcessor:
        return self._sink


async def run_meet_pipeline(
    audio_queue: asyncio.Queue,
    on_transcript=None,
    on_assistant=None,
):
    """Run the ginjoly meeting agent over audio coming from `audio_queue`.

    on_transcript(text) fires for every final transcription line; on_assistant(text)
    fires with the bot's reply after it handles an addressed request.
    """
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

    from app.config import get_settings
    from app.meeting.pipeline import build_meeting_pipeline
    from pipecat.workers.runner import WorkerRunner

    settings = get_settings()
    transport = MeetTransport(audio_queue, sample_rate=settings.meeting_sample_rate)

    worker, _session = build_meeting_pipeline(
        transport,
        on_transcript=on_transcript,
        on_assistant=on_assistant,
    )

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
