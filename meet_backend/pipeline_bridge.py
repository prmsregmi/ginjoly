"""
Bridge between the Meet audio capture and the ginjoly pipecat pipeline.

MeetTransport is a minimal pipecat BaseTransport whose input() pumps
AudioRawFrames from an asyncio.Queue fed by meet_bot.py.
"""

import asyncio
import sys
import os

# Add ginjoly to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ginjoly", "server"))

from pipecat.frames.frames import AudioRawFrame, EndFrame, StartFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.base_transport import BaseTransport, TransportParams


class MeetAudioSource(FrameProcessor):
    """Reads raw PCM bytes from a queue and pushes AudioRawFrames downstream."""

    def __init__(self, queue: asyncio.Queue, **kwargs):
        super().__init__(**kwargs)
        self._queue = queue
        self._pump_task: asyncio.Task | None = None

    async def start(self, clock):
        await super().start(clock)
        self._pump_task = asyncio.create_task(self._pump())

    async def stop(self, clock):
        if self._pump_task:
            self._pump_task.cancel()
        await super().stop(clock)

    async def process_frame(self, frame, direction):
        await self.push_frame(frame, direction)

    async def _pump(self):
        while True:
            data = await self._queue.get()
            if data is None:
                await self.push_frame(EndFrame())
                break
            frame = AudioRawFrame(audio=data, sample_rate=16000, num_channels=1)
            await self.push_frame(frame)


class NullOutput(FrameProcessor):
    """Discards all frames (TTS output — injecting back into Meet comes later)."""

    async def process_frame(self, frame, direction):
        pass  # drop everything


class MeetTransport(BaseTransport):
    """Minimal transport that bridges our Meet audio queue into pipecat."""

    def __init__(self, audio_queue: asyncio.Queue, **kwargs):
        super().__init__(**kwargs)
        self._source = MeetAudioSource(audio_queue, name="MeetAudioSource")
        self._sink = NullOutput(name="NullOutput")

    def input(self) -> FrameProcessor:
        return self._source

    def output(self) -> FrameProcessor:
        return self._sink


async def run_meet_pipeline(audio_queue: asyncio.Queue, on_transcript=None):
    """
    Start the ginjoly pipeline with audio from audio_queue.
    on_transcript(text) is called whenever the STT produces a final transcript.
    """
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

    # Import ginjoly modules
    from app.config import get_settings
    from app.session import SessionState
    from app.contexts.hackathon import HACKATHON_CONTEXT
    from app.flow import build_flow_manager, make_collect_anchors_node
    from app.llm_factory import build_llm
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import TTSSpeakFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.workers.runner import WorkerRunner

    settings = get_settings()
    session = SessionState(HACKATHON_CONTEXT)
    transport = MeetTransport(audio_queue)

    from bot import build_stt
    stt = build_stt(settings)
    llm = build_llm(settings)

    context = LLMContext()
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    # Wire transcript callback if provided
    if on_transcript:
        from pipecat.frames.frames import TranscriptionFrame, InterimTranscriptionFrame

        original_push = stt.push_frame

        async def intercepting_push(frame, direction=FrameDirection.DOWNSTREAM):
            if isinstance(frame, TranscriptionFrame) and frame.text:
                await on_transcript(frame.text)
            await original_push(frame, direction)

        stt.push_frame = intercepting_push

    pipeline = Pipeline([
        transport.input(),
        stt,
        context_aggregator.user(),
        llm,
        transport.output(),
        context_aggregator.assistant(),
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=False),
    )

    flow_manager = build_flow_manager(task, llm, context_aggregator, transport)

    # Initialize flow immediately (no browser client_ready event needed)
    await flow_manager.initialize(make_collect_anchors_node(session))
    await task.queue_frames([TTSSpeakFrame(session.context.intro_script)])

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(task)
    await runner.run()
