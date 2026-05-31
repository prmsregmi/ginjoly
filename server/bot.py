"""Pipecat Cloud entrypoint for the carleton meeting agent.

Pipecat Cloud runs one containerized bot per session that JOINS A DAILY ROOM —
it cannot run the local Playwright Google-Meet bridge (connector/bridge), so in
the cloud the "meeting" is a Daily WebRTC room. The voice pipeline itself
(VAD -> STT -> WakeNameGate -> TTS) is transport-agnostic and is reused verbatim
via build_meeting_pipeline; only the transport differs (DailyTransport here vs
MeetTransport in the local bridge).

Cekura (optional): when CEKURA_API_KEY and CEKURA_PIPECAT_AGENT_ID are set, the
PipecatTracer is attached so every call's transcript lands in the Cekura
dashboard. User turns are captured from pipecat turn events; the bot's spoken
replies are mirrored into an LLMContext the tracer watches (this pipeline has no
in-path LLM, so there is no context otherwise). MCP tool calls run in the brain
subprocess off-pipeline and are NOT visible to the tracer. The hosted Cekura
simulation (select "Pipecat" as the provider) drives this same deployed agent
over Daily and scores it independently of the tracer.
"""

from loguru import logger
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.runner.types import DailyRunnerArguments, RunnerArguments
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.workers.runner import WorkerRunner

from app.config import Settings, get_settings
from app.meeting.pipeline import build_meeting_pipeline


def _make_cekura_capture(settings: Settings):
    """If Cekura is configured, return (tracer, context, on_assistant); else
    (None, None, None). on_assistant mirrors the bot's spoken replies into the
    context so the tracer's assistant-turn capture (which diffs context.messages)
    sees them — this pipeline has no in-path LLM to populate a context otherwise.
    """
    if not (settings.cekura_api_key and settings.cekura_pipecat_agent_id):
        return None, None, None
    try:
        from cekura.pipecat import PipecatTracer

        tracer = PipecatTracer(
            api_key=settings.cekura_api_key,
            agent_id=settings.cekura_pipecat_agent_id,
        )
        context = LLMContext()

        async def on_assistant(text: str):
            context.messages.append({"role": "assistant", "content": text})

        return tracer, context, on_assistant
    except Exception as exc:  # SDK import/init must never break the deployed bot
        logger.warning(f"cekura: init failed, running untraced: {exc!r}")
        return None, None, None


async def bot(runner_args: RunnerArguments):
    """Pipecat Cloud entry point. Joins the Daily room and runs the meeting agent."""
    settings = get_settings()

    if not isinstance(runner_args, DailyRunnerArguments):
        # The meeting agent is voice-only over Daily WebRTC; other transports
        # (websocket/dial-in) aren't wired for the cloud deploy.
        raise RuntimeError(f"Unsupported transport for carleton: {type(runner_args).__name__}")

    transport = DailyTransport(
        runner_args.room_url,
        runner_args.token,
        settings.meeting_bot_name,
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            # Match the in-pipeline VAD (16 kHz) and Gradium TTS playback (48 kHz);
            # pipecat resamples anything Daily delivers at a different rate.
            audio_in_sample_rate=settings.meeting_sample_rate,
            audio_out_sample_rate=settings.meeting_playback_sample_rate,
        ),
    )

    tracer, context, on_assistant = _make_cekura_capture(settings)
    worker, _session = build_meeting_pipeline(transport, on_assistant=on_assistant)

    if tracer is not None:
        try:
            attach = tracer.observe_pipeline if settings.cekura_record_audio else tracer.track_pipeline
            attach(worker.pipeline, context)
            # PipelineTask subclasses PipelineWorker, so the worker is accepted here.
            tracer.register_task_handlers(worker, transport=transport)
            logger.info(f"cekura: tracer attached (agent_id={settings.cekura_pipecat_agent_id})")
        except Exception as exc:  # a tracer mismatch must not take the bot down
            logger.warning(f"cekura: tracer attach failed, running untraced: {exc!r}")

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()
