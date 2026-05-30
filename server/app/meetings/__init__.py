"""Meeting ingestion: Recall.ai transcript + calendar -> normalized Transcript."""

from app.meetings.schema import (
    Attendee,
    AttributionSource,
    MeetingMeta,
    SpeakerAttribution,
    SpeakerMap,
    Transcript,
    Utterance,
)

__all__ = [
    "AttributionSource",
    "Attendee",
    "MeetingMeta",
    "SpeakerAttribution",
    "SpeakerMap",
    "Transcript",
    "Utterance",
]
