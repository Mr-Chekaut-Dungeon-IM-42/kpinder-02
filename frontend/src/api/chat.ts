import { requestJson } from "./client";

export interface Message {
  id: string;
  match_id: string;
  sender_id: string;
  client_message_id: string;
  content: string;
  created_at: string;
  edited_at: string | null;
}

export interface MessagesPage {
  items: Message[];
  next_cursor: string | null;
}

export function getMessages(
  token: string,
  matchId: string,
  cursor?: string | null,
): Promise<MessagesPage> {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return requestJson<MessagesPage>(
    "GET",
    `/chat/${matchId}/messages${query}`,
    undefined,
    token,
  );
}

export function sendMessage(
  token: string,
  matchId: string,
  content: string,
  clientMessageId: string = crypto.randomUUID(),
): Promise<Message> {
  return requestJson<Message>(
    "POST",
    `/chat/${matchId}/messages`,
    {
      client_message_id: clientMessageId,
      content,
    },
    token,
  );
}

export function editMessage(
  token: string,
  messageId: string,
  content: string,
): Promise<Message> {
  return requestJson<Message>(
    "PATCH",
    `/chat/messages/${messageId}`,
    { content },
    token,
  );
}

export function deleteMessage(token: string, messageId: string): Promise<void> {
  return requestJson<void>(
    "DELETE",
    `/chat/messages/${messageId}`,
    undefined,
    token,
  );
}

export function searchMessages(
  token: string,
  matchId: string,
  query: string,
): Promise<Message[]> {
  const qs = `?q=${encodeURIComponent(query)}`;
  return requestJson<Message[]>(
    "GET",
    `/chat/${matchId}/messages/search${qs}`,
    undefined,
    token,
  );
}
