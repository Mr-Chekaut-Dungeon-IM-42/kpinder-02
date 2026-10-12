import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import service
from app.chat.schemas import (
    MessageEditRequest,
    MessageResponse,
    MessageSendRequest,
    MessagesPage,
)
from app.shared.db import get_db
from app.shared.jwt_dep import get_current_user_id, get_current_user_id_ws
from app.shared.ws import ws_manager

router = APIRouter(tags=["chat"])


@router.post(
    "/chat/{match_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    match_id: uuid.UUID,
    data: MessageSendRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MessageResponse:
    return await service.send_message(db, user_id, match_id, data)


@router.get(
    "/chat/{match_id}/messages",
    response_model=MessagesPage,
)
async def get_messages(
    match_id: uuid.UUID,
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MessagesPage:
    return await service.get_messages(db, user_id, match_id, cursor)


@router.patch(
    "/chat/messages/{message_id}",
    response_model=MessageResponse,
)
async def edit_message(
    message_id: uuid.UUID,
    data: MessageEditRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> MessageResponse:
    return await service.edit_message(db, user_id, message_id, data)


@router.delete(
    "/chat/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_message(
    message_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> None:
    await service.delete_message(db, user_id, message_id)


@router.get(
    "/chat/{match_id}/messages/search",
    response_model=list[MessageResponse],
)
async def search_messages(
    match_id: uuid.UUID,
    q: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[MessageResponse]:
    return await service.search_messages(db, user_id, match_id, q)


@router.websocket("/ws")
@router.websocket("/chat/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    try:
        user_id = get_current_user_id_ws(token)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
