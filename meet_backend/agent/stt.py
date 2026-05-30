import asyncio
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from config import settings


async def start_deepgram_stream(transcript_callback):
    """
    Returns a callable `send_audio(pcm_bytes)` that feeds audio to Deepgram.
    Calls transcript_callback(text, speaker) when a final transcript is ready.
    """
    dg = DeepgramClient(settings.deepgram_api_key)
    connection = dg.listen.asyncwebsocket.v("1")

    async def on_message(self, result, **kwargs):
        sentence = result.channel.alternatives[0].transcript
        if not sentence or not result.is_final:
            return
        speaker = getattr(result.channel.alternatives[0].words[0], "speaker", 0) if result.channel.alternatives[0].words else 0
        await transcript_callback(sentence, speaker)

    connection.on(LiveTranscriptionEvents.Transcript, on_message)

    options = LiveOptions(
        model="nova-2",
        language="en",
        encoding="linear16",
        sample_rate=16000,
        channels=1,
        diarize=True,
        interim_results=False,
        endpointing=500,
    )

    await connection.start(options)

    async def send_audio(pcm_bytes: bytes):
        await connection.send(pcm_bytes)

    return send_audio, connection
