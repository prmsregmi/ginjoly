"""Swappable TTS for the meeting agent.

Default is Gradium (streams 48 kHz mono PCM, matching the Meet playback rate, so
no resampling is needed on the way out). `tts_provider="cartesia"` swaps in the
prior Cartesia baseline. The provider is read from `settings.tts_provider` so
the pipeline stays identical across providers.
"""

from app.config import Settings


def build_tts(settings: Settings):
    """Build the TTS service for the configured provider."""
    if settings.tts_provider.lower() == "cartesia":
        from pipecat.services.cartesia.tts import CartesiaTTSService

        return CartesiaTTSService(
            api_key=settings.cartesia_api_key,
            settings=CartesiaTTSService.Settings(voice=settings.cartesia_voice_id),
        )

    # Gradium (default). Omit the voice setting to use the service default voice.
    from pipecat.services.gradium.tts import GradiumTTSService

    if settings.gradium_voice:
        return GradiumTTSService(
            api_key=settings.gradium_api_key,
            settings=GradiumTTSService.Settings(voice=settings.gradium_voice),
        )
    return GradiumTTSService(api_key=settings.gradium_api_key)
