import { useEffect, useRef, useCallback } from "react";

type MessageHandler = (data: Record<string, unknown>) => void;

export function useWebSocket(onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  const connect = useCallback(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        handlerRef.current(JSON.parse(e.data));
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      // Reconnect after 3 s
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    // Keep-alive ping every 25 s
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 25000);

    ws.onopen = () => clearInterval(ping); // only one ping interval at a time
    ws.addEventListener("open", () => {
      const id = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 25000);
      ws.addEventListener("close", () => clearInterval(id));
    });
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
