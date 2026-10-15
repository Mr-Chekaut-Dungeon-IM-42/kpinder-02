import base64
import json
import uuid
from datetime import datetime

from fastapi import HTTPException, status

from app.shared.models import Match


def encode_cursor(created_at: datetime, message_id: uuid.UUID) -> str:
    payload = json.dumps({"created_at": created_at.isoformat(), "id": str(message_id)})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["created_at"]), uuid.UUID(payload["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid cursor"
        ) from exc


def assert_participant(match: Match, caller_id: uuid.UUID) -> uuid.UUID:
    if match.user_a_id != caller_id and match.user_b_id != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a participant in this conversation",
        )
    return match.user_b_id if match.user_a_id == caller_id else match.user_a_id
