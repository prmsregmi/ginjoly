from anthropic import AsyncAnthropic
from config import settings

client = AsyncAnthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """You are an AI meeting assistant. You are currently in a live meeting.
You listen to the conversation and respond when someone addresses you (e.g. "Hey AI", "Assistant", or asks you a question).
Keep responses concise and natural — you are speaking, not writing.
You have access to company context and can take actions like creating tickets.
If you are not sure you were addressed, stay silent by returning an empty string."""

conversation_history = []


async def should_respond(transcript: str) -> bool:
    """Quick cheap check — did someone address the assistant?"""
    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{
            "role": "user",
            "content": f'Did someone address an AI assistant in this transcript? Reply only "yes" or "no".\n\nTranscript: "{transcript}"'
        }]
    )
    return resp.content[0].text.strip().lower() == "yes"


async def get_response(transcript: str, context: str = "") -> str:
    conversation_history.append({"role": "user", "content": transcript})

    system = SYSTEM_PROMPT
    if context:
        system += f"\n\nRelevant company context:\n{context}"

    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=system,
        messages=conversation_history,
    )

    reply = resp.content[0].text.strip()
    if reply:
        conversation_history.append({"role": "assistant", "content": reply})

    return reply
