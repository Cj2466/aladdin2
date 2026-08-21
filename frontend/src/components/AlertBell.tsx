import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listAlertEvents } from "../api/client";
import { AlertsPanel } from "./AlertsPanel";

export function AlertBell() {
  const [isOpen, setIsOpen] = useState(false);

  const { data: events } = useQuery({
    queryKey: ["alertEvents"],
    queryFn: listAlertEvents,
    refetchInterval: 60_000,
  });

  const unreadCount = events?.filter((e) => !e.is_read).length ?? 0;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="relative text-sm px-3 py-1.5 rounded-md"
        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
      >
        Alerts
        {unreadCount > 0 && (
          <span
            className="absolute -top-1.5 -right-1.5 rounded-full text-[10px] leading-none px-1.5 py-1 text-white"
            style={{ background: "var(--status-critical)" }}
          >
            {unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className="absolute right-0 mt-2 w-96 rounded-lg p-4 shadow-lg z-10"
          style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
        >
          <AlertsPanel events={events ?? []} />
        </div>
      )}
    </div>
  );
}
