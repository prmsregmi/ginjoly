"""Swappable STT for the meeting agent.

Default is Gradium. `stt_provider="nemotron"` swaps in NVIDIA Speech Streaming
over a websocket (drives its own turn finalization — hard reset on VAD stop ->
finalized=True TranscriptionFrame); `stt_provider="deepgram"` is the prior
baseline. The provider is read from `settings.stt_provider` so callers stay
identical across providers.
"""

from app.config import Settings


def build_stt(settings: Settings):
    """Build the STT service for the configured provider."""
    provider = settings.stt_provider.lower()

    if provider == "nemotron":
        from app.services.nvidia_stt import NVidiaWebSocketSTTService

        return NVidiaWebSocketSTTService(
            url=settings.nvidia_asr_url,
            strip_interim_prefix=True,
        )

    if provider == "deepgram":
        from pipecat.services.deepgram.stt import DeepgramSTTService

        return DeepgramSTTService(api_key=settings.deepgram_api_key)

    # Gradium (default). Mixed Meet audio arrives as 16 kHz mono PCM; Gradium
    # accepts 8/16/24 kHz, so pass the meeting rate through explicitly.
    from pipecat.services.gradium.stt import GradiumSTTService

    return GradiumSTTService(
        api_key=settings.gradium_api_key,
        sample_rate=settings.meeting_sample_rate,
    )
