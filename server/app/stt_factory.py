"""Swappable STT for the meeting agent.

Baseline is Deepgram. `stt_provider="nemotron"` swaps in NVIDIA Speech
Streaming over a websocket; that service drives its own turn finalization
(hard reset on VAD stop -> finalized=True TranscriptionFrame), which pairs with
the default smart-turn stop strategy. The provider is read from
`settings.stt_provider` so callers stay identical across providers.
"""

from app.config import Settings


def build_stt(settings: Settings):
    """Build the STT service for the configured provider."""
    if settings.stt_provider.lower() == "nemotron":
        from app.services.nvidia_stt import NVidiaWebSocketSTTService

        return NVidiaWebSocketSTTService(
            url=settings.nvidia_asr_url,
            strip_interim_prefix=True,
        )

    from pipecat.services.deepgram.stt import DeepgramSTTService

    return DeepgramSTTService(api_key=settings.deepgram_api_key)
