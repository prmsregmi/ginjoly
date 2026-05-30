from elevenlabs.client import AsyncElevenLabs
from config import settings

client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)


async def speak(text: str) -> bytes:
    """Returns MP3 audio bytes for the given text."""
    audio_chunks = []
    async for chunk in await client.text_to_speech.convert(
        voice_id=settings.elevenlabs_voice_id,
        text=text,
        model_id="eleven_turbo_v2",
        output_format="mp3_44100_128",
    ):
        audio_chunks.append(chunk)
    return b"".join(audio_chunks)
