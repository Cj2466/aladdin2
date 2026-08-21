import { useEffect, useRef, useState } from "react";
import { liveQuotesWsUrl } from "../api/client";

export interface LiveQuote {
  price: number;
  previousClose: number;
  changePercent: number; // percent units already, e.g. 0.95 means +0.95%
  marketState: "open" | "closed";
  lastUpdated: number; // ms since epoch
  status: "pending" | "ok" | "invalid";
}

export type ConnectionState = "connecting" | "open" | "reconnecting" | "unavailable";

const MAX_BACKOFF_MS = 30_000;
const SUBSCRIBE_DEBOUNCE_MS = 500;

function normalizeTickers(tickers: string[]): string[] {
  return Array.from(new Set(tickers.map((t) => t.trim().toUpperCase()).filter(Boolean))).sort();
}

function pendingQuote(): LiveQuote {
  return {
    price: 0,
    previousClose: 0,
    changePercent: 0,
    marketState: "closed",
    lastUpdated: 0,
    status: "pending",
  };
}

export function useLiveQuotes(tickers: string[]): {
  quotes: Record<string, LiveQuote>;
  connectionState: ConnectionState;
} {
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({});
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");

  const wsRef = useRef<WebSocket | null>(null);
  const tickersRef = useRef<string[]>([]);
  const retryCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unavailableRef = useRef(false);
  const closedByUsRef = useRef(false);

  const normalizedTickers = normalizeTickers(tickers);
  const normalizedKey = normalizedTickers.join(",");

  useEffect(() => {
    tickersRef.current = normalizedKey ? normalizedKey.split(",") : [];
  }, [normalizedKey]);

  // Debounced subscribe: sends the current ticker list over an already-open
  // socket whenever it actually changes, without thrashing on every keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      const ws = wsRef.current;
      const desired = tickersRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "subscribe", tickers: desired }));
        setQuotes((prev) => {
          const next = { ...prev };
          for (const ticker of desired) {
            if (!next[ticker]) next[ticker] = pendingQuote();
          }
          return next;
        });
      }
    }, SUBSCRIBE_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [normalizedKey]);

  // Connection lifecycle: owns open/close, runs once on mount. Ticker
  // changes are handled by the effect above over the same open socket.
  useEffect(() => {
    closedByUsRef.current = false;

    function scheduleReconnect() {
      setConnectionState("reconnecting");
      const attempt = retryCountRef.current + 1;
      retryCountRef.current = attempt;
      const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** (attempt - 1)) + Math.random() * 500;
      reconnectTimerRef.current = setTimeout(connect, delay);
    }

    function connect() {
      if (closedByUsRef.current) return;
      setConnectionState(retryCountRef.current === 0 ? "connecting" : "reconnecting");

      const ws = new WebSocket(liveQuotesWsUrl());
      wsRef.current = ws;

      // Every handler guards on `wsRef.current !== ws` so events from a
      // socket that's since been superseded (StrictMode double-mount, or a
      // reconnect that raced a fresh connect) are ignored rather than
      // corrupting state meant for the current connection.
      ws.onopen = () => {
        if (wsRef.current !== ws) return;
        retryCountRef.current = 0;
        setConnectionState("open");
        if (tickersRef.current.length > 0) {
          ws.send(JSON.stringify({ type: "subscribe", tickers: tickersRef.current }));
        }
      };

      ws.onmessage = (event) => {
        if (wsRef.current !== ws) return;
        let message: Record<string, unknown>;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }

        if (message.type === "error" && message.code === "not_configured") {
          unavailableRef.current = true;
          setConnectionState("unavailable");
          return;
        }

        if (message.type === "error" && typeof message.ticker === "string") {
          const ticker = message.ticker;
          setQuotes((prev) => ({
            ...prev,
            [ticker]: { ...pendingQuote(), status: "invalid", lastUpdated: Date.now() },
          }));
          return;
        }

        if (message.type === "snapshot" || message.type === "tick") {
          const ticker = message.ticker as string;
          setQuotes((prev) => ({
            ...prev,
            [ticker]: {
              price: message.price as number,
              previousClose: message.previous_close as number,
              changePercent: message.change_percent as number,
              marketState: message.market_state as "open" | "closed",
              lastUpdated: (message.last_updated as number) * 1000,
              status: "ok",
            },
          }));
        }
      };

      ws.onclose = () => {
        if (wsRef.current !== ws) return;
        if (closedByUsRef.current || unavailableRef.current) return;
        scheduleReconnect();
      };

      ws.onerror = () => {
        if (wsRef.current !== ws) return;
        ws.close();
      };
    }

    connect();

    return () => {
      closedByUsRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, []);

  return { quotes, connectionState };
}
