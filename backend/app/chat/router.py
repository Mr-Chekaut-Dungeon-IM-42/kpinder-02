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

from app.chat.commands import (
    DeleteMessageCommand,
    EditMessageCommand,
    SendMessageCommand,
    get_delete_message_command,
    get_edit_message_command,
    get_send_message_command,
)
from app.chat.queries import (
    GetMessagesQuery,
    SearchMessagesQuery,
    get_messages_query,
    get_search_messages_query,
)
from app.chat.schemas import (
    MessageEditRequest,
    MessageResponse,
    MessageSendRequest,
    MessagesPage,
)
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
    user_id: uuid.UUID = Depends(get_current_user_id),
    command: SendMessageCommand = Depends(get_send_message_command),
) -> MessageResponse:
    return await command.execute(user_id, match_id, data)


@router.get(
    "/chat/{match_id}/messages",
    response_model=MessagesPage,
)
async def get_messages(
    match_id: uuid.UUID,
    cursor: str | None = Query(default=None),
    user_id: uuid.UUID = Depends(get_current_user_id),
    query: GetMessagesQuery = Depends(get_messages_query),
) -> MessagesPage:
    return await query.execute(user_id, match_id, cursor)


@router.patch(
    "/chat/messages/{message_id}",
    response_model=MessageResponse,
)
async def edit_message(
    message_id: uuid.UUID,
    data: MessageEditRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    command: EditMessageCommand = Depends(get_edit_message_command),
) -> MessageResponse:
    return await command.execute(user_id, message_id, data)


@router.delete(
    "/chat/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_message(
    message_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    command: DeleteMessageCommand = Depends(get_delete_message_command),
) -> None:
    await command.execute(user_id, message_id)


@router.get(
    "/chat/{match_id}/messages/search",
    response_model=list[MessageResponse],
)
async def search_messages(
    match_id: uuid.UUID,
    q: str = Query(default=""),
    user_id: uuid.UUID = Depends(get_current_user_id),
    query: SearchMessagesQuery = Depends(get_search_messages_query),
) -> list[MessageResponse]:
    return await query.execute(user_id, match_id, q)


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
