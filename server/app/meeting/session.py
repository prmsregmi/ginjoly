"""Per-connection state for one meeting.

A rolling transcript (so the brain has "what we just discussed" context), the
list of actions taken, and a short memory of the bot's own recent speech used
by the self-echo filter on a mixed stream.
"""

import uuid
from collections import deque
from datetime import UTC, datetime


def _new_call_id() -> str:
    return f"{int(datetime.now(UTC).timestamp())}-{uuid.uuid4().hex[:8]}"


class MeetingSessionState:
    def __init__(self, *, transcript_window: int = 12):
        self.call_id = _new_call_id()
        self.transcript: deque[str] = deque(maxlen=transcript_window)
        self.actions: list[tuple[str, str]] = []
        # Bot's own recent spoken lines (lower-cased) for the echo filter.
        self.recent_tts: deque[str] = deque(maxlen=8)

    def add_line(self, text: str) -> None:
        self.transcript.append(text)

    def recent_transcript(self) -> str:
        return "\n".join(self.transcript)

    def note_spoken(self, text: str) -> None:
        self.recent_tts.append(text.strip().lower())

    def record_action(self, request: str, summary: str) -> None:
        self.actions.append((request, summary))
