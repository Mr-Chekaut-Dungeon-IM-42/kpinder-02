import { useEffect, useRef, useState } from "react";
import { API_URL } from "../api/client";

export interface WebSocketEvent<T = unknown> {
  event: string;
  data: T;
}

export function useWebSocket(
  token: string | null,
  onEvent?: (event: WebSocketEvent) => void,
) {
  const [isConnected, setIsConnected] = useState(false);
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!token) {
      return;
    }

    let isMounted = true;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    let ws: WebSocket | null = null;

    function connect() {
      if (!isMounted || !token) return;

      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = API_URL.replace(/^http(s?):\/\//, "");
      const wsUrl = `${wsProtocol}//${host}/ws?token=${encodeURIComponent(token)}`;

      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (!isMounted) {
          ws?.close();
          return;
        }
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as WebSocketEvent;
          onEventRef.current?.(parsed);
        } catch {
          // Ignore unparseable frames
        }
      };

      ws.onclose = () => {
        if (!isMounted) return;
        setIsConnected(false);
        // Attempt reconnect after 3 seconds
        reconnectTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws?.close();
      };
    }

    connect();

    return () => {
      isMounted = false;
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      ws?.close();
      setIsConnected(false);
    };
  }, [token]);

  return { isConnected };
}
