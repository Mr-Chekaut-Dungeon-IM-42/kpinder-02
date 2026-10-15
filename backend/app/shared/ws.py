import uuid
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """In-memory WebSocket connection registry (single-process MVP)."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[user_id].discard(websocket)
        if not self._connections[user_id]:
            self._connections.pop(user_id, None)

    def is_connected(self, user_id: uuid.UUID) -> bool:
        return bool(self._connections.get(user_id))

    async def send_event(self, user_id: uuid.UUID, event: str, data: dict) -> None:
        sockets = list(self._connections.get(user_id, set()))
        if not sockets:
            return

        payload = {"event": event, "data": data}
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(user_id, ws)


ws_manager = ConnectionManager()
