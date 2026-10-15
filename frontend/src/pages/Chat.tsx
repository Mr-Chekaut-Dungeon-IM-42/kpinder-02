import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, Navigate, useLocation, useParams } from "react-router-dom";
import {
  deleteMessage,
  editMessage,
  getMessages,
  searchMessages,
  sendMessage,
  type Message,
} from "../api/chat";
import type { MatchUser } from "../api/matching";
import { useAuth } from "../auth/AuthContext";
import NavBar from "../components/NavBar";
import { useWebSocket, type WebSocketEvent } from "../hooks/useWebSocket";
import styles from "./Chat.module.css";

function parseUserId(token: string): string | null {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    const payload = JSON.parse(atob(parts[1]));
    return payload.sub ?? null;
  } catch {
    return null;
  }
}

export default function Chat() {
  const { token } = useAuth();
  const { matchId } = useParams<{ matchId: string }>();
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (!matchId) {
    return <Navigate to="/matches" replace />;
  }

  const otherUser = (location.state as { otherUser?: MatchUser } | null)
    ?.otherUser;

  return (
    <ChatView
      token={token}
      matchId={matchId}
      initialOtherUser={otherUser ?? null}
    />
  );
}

interface ChatViewProps {
  token: string;
  matchId: string;
  initialOtherUser: MatchUser | null;
}

function ChatView({ token, matchId, initialOtherUser }: ChatViewProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [inputContent, setInputContent] = useState("");
  const [sending, setSending] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<Message[] | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevScrollHeightRef = useRef<number | null>(null);
  const isInitialLoadRef = useRef(true);

  const currentUserId = useMemo(() => parseUserId(token), [token]);

  const handleWsEvent = useCallback(
    (event: WebSocketEvent) => {
      const data = event.data as Partial<Message>;
      if (data.match_id && data.match_id !== matchId) {
        return;
      }

      if (event.event === "new_message") {
        const newMsg = event.data as Message;
        const container = containerRef.current;
        const isNearBottom = container
          ? container.scrollHeight -
              container.scrollTop -
              container.clientHeight <
            150
          : true;

        setMessages((prev) => {
          if (
            prev.some(
              (m) =>
                m.id === newMsg.id ||
                m.client_message_id === newMsg.client_message_id,
            )
          ) {
            return prev;
          }
          return [...prev, newMsg];
        });

        if (isNearBottom) {
          requestAnimationFrame(() => {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
          });
        }
      } else if (event.event === "message_edited") {
        const edited = event.data as Message;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === edited.id
              ? { ...m, content: edited.content, edited_at: edited.edited_at }
              : m,
          ),
        );
      } else if (event.event === "message_deleted") {
        const deleted = event.data as { id: string };
        setMessages((prev) => prev.filter((m) => m.id !== deleted.id));
      }
    },
    [matchId],
  );

  const { isConnected } = useWebSocket(token, handleWsEvent);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const page = await getMessages(token, matchId);
        // Page items arrive newest-first; reverse to display chronologically
        setMessages([...page.items].reverse());
        setCursor(page.next_cursor);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load messages.",
        );
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [token, matchId]);

  // Scroll to bottom only on initial load
  useEffect(() => {
    if (!loading && isInitialLoadRef.current) {
      messagesEndRef.current?.scrollIntoView();
      isInitialLoadRef.current = false;
    }
  }, [loading]);

  // Preserve scroll position when older messages are prepended
  useLayoutEffect(() => {
    if (prevScrollHeightRef.current !== null && containerRef.current) {
      const newScrollHeight = containerRef.current.scrollHeight;
      containerRef.current.scrollTop =
        newScrollHeight - prevScrollHeightRef.current;
      prevScrollHeightRef.current = null;
    }
  }, [messages]);

  async function handleLoadOlder() {
    if (!cursor || loadingOlder || !containerRef.current) return;
    setLoadingOlder(true);
    prevScrollHeightRef.current = containerRef.current.scrollHeight;

    try {
      const page = await getMessages(token, matchId, cursor);
      // Prepend older messages
      setMessages((prev) => [...[...page.items].reverse(), ...prev]);
      setCursor(page.next_cursor);
    } catch (err) {
      prevScrollHeightRef.current = null;
      setError(
        err instanceof Error ? err.message : "Failed to load older messages.",
      );
    } finally {
      setLoadingOlder(false);
    }
  }

  async function handleSend(e: FormEvent) {
    e.preventDefault();
    const trimmed = inputContent.trim();
    if (!trimmed || sending) return;

    setSending(true);
    setError(null);
    try {
      const sent = await sendMessage(token, matchId, trimmed);
      setMessages((prev) => {
        if (prev.some((m) => m.id === sent.id)) return prev;
        return [...prev, sent];
      });
      setInputContent("");
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setSending(false);
    }
  }

  async function handleSaveEdit(messageId: string) {
    const trimmed = editContent.trim();
    if (!trimmed) return;

    try {
      const updated = await editMessage(token, messageId, trimmed);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? { ...m, content: updated.content, edited_at: updated.edited_at }
            : m,
        ),
      );
      setEditingId(null);
      setEditContent("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to edit message.");
    }
  }

  async function handleDelete(messageId: string) {
    try {
      await deleteMessage(token, messageId);
      setMessages((prev) => prev.filter((m) => m.id !== messageId));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete message.",
      );
    }
  }

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }

    setIsSearching(true);
    try {
      const results = await searchMessages(token, matchId, searchQuery.trim());
      setSearchResults([...results].reverse());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setIsSearching(false);
    }
  }

  function handleClearSearch() {
    setSearchQuery("");
    setSearchResults(null);
  }

  const displayedMessages = searchResults ?? messages;

  return (
    <div className={styles.page}>
      <NavBar />
      <div className={styles.chatContainer}>
        <div className={styles.header}>
          <div className={styles.partnerInfo}>
            <Link to="/matches" className={styles.backLink}>
              ← Matches
            </Link>
            {initialOtherUser?.photo_url && (
              <img
                src={initialOtherUser.photo_url}
                alt=""
                className={styles.partnerPhoto}
              />
            )}
            <span className={styles.partnerName}>
              {initialOtherUser?.name ?? "Chat"}
            </span>
          </div>
          <div className={styles.statusIndicator}>
            <span
              className={isConnected ? styles.liveDot : styles.offlineDot}
            />
            {isConnected ? "Live" : "Connecting…"}
          </div>
        </div>

        <form className={styles.searchBar} onSubmit={handleSearch}>
          <input
            className={styles.searchInput}
            type="text"
            placeholder="Search conversation…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              type="button"
              className={styles.clearSearchBtn}
              onClick={handleClearSearch}
            >
              Clear
            </button>
          )}
        </form>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.messagesList} ref={containerRef}>
          {!searchResults && cursor && (
            <button
              className={styles.loadOlderBtn}
              onClick={handleLoadOlder}
              disabled={loadingOlder}
            >
              {loadingOlder ? "Loading older…" : "Load older messages"}
            </button>
          )}

          {loading ? (
            <p className={styles.emptyPrompt}>Loading messages…</p>
          ) : displayedMessages.length === 0 ? (
            <p className={styles.emptyPrompt}>
              {searchResults ? "No matching messages found." : "Say hello!"}
            </p>
          ) : (
            displayedMessages.map((msg) => {
              const isMine = currentUserId
                ? msg.sender_id === currentUserId
                : false;
              const isEditing = editingId === msg.id;

              return (
                <div
                  key={msg.id}
                  className={`${styles.messageRow} ${isMine ? styles.mine : styles.theirs}`}
                >
                  {isEditing ? (
                    <div className={styles.editForm}>
                      <input
                        className={styles.editInput}
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        autoFocus
                      />
                      <button
                        className={styles.saveBtn}
                        onClick={() => handleSaveEdit(msg.id)}
                      >
                        Save
                      </button>
                      <button
                        className={styles.cancelBtn}
                        onClick={() => setEditingId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className={styles.bubble}>{msg.content}</div>
                      <div className={styles.messageMeta}>
                        <span>
                          {new Date(msg.created_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        {msg.edited_at && <span>(edited)</span>}
                        {isMine && !searchResults && (
                          <>
                            <button
                              className={styles.actionBtn}
                              onClick={() => {
                                setEditingId(msg.id);
                                setEditContent(msg.content);
                              }}
                            >
                              edit
                            </button>
                            <button
                              className={`${styles.actionBtn} ${styles.deleteBtn}`}
                              onClick={() => handleDelete(msg.id)}
                            >
                              delete
                            </button>
                          </>
                        )}
                      </div>
                    </>
                  )}
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        <form className={styles.inputArea} onSubmit={handleSend}>
          <input
            className={styles.messageInput}
            type="text"
            placeholder="Type a message…"
            value={inputContent}
            onChange={(e) => setInputContent(e.target.value)}
            disabled={sending || isSearching}
          />
          <button
            type="submit"
            className={styles.sendBtn}
            disabled={sending || !inputContent.trim()}
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
