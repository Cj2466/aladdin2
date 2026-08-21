import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  createAlertRule,
  deleteAlertRule,
  listAlertRules,
  listPortfolios,
  markAlertEventRead,
  RISK_METRIC_OPTIONS,
} from "../api/client";
import type { AlertDirection, AlertEventOut, AlertRuleType, ApiErrorBody } from "../api/client";

interface AlertsPanelProps {
  events: AlertEventOut[];
}

const inputStyle = {
  background: "var(--page-plane)",
  border: "1px solid var(--border)",
  color: "var(--text-primary)",
};

export function AlertsPanel({ events }: AlertsPanelProps) {
  const queryClient = useQueryClient();

  const { data: rules } = useQuery({ queryKey: ["alertRules"], queryFn: listAlertRules });
  const { data: portfolios } = useQuery({ queryKey: ["portfolios"], queryFn: listPortfolios });

  const [portfolioId, setPortfolioId] = useState<number | "">("");
  const [ruleType, setRuleType] = useState<AlertRuleType>("price_move");
  const [ticker, setTicker] = useState("");
  const [metric, setMetric] = useState<string>(RISK_METRIC_OPTIONS[0]);
  const [thresholdPct, setThresholdPct] = useState(5);
  const [direction, setDirection] = useState<AlertDirection>("up");

  const createMutation = useMutation({
    mutationFn: () => {
      if (!portfolioId) throw new Error("Choose a portfolio");
      return createAlertRule({
        portfolio_id: portfolioId,
        rule_type: ruleType,
        ticker: ruleType === "price_move" ? ticker.trim().toUpperCase() : undefined,
        metric: ruleType === "risk_metric" ? metric : undefined,
        threshold_pct: thresholdPct,
        direction,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alertRules"] });
      setTicker("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteAlertRule(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alertRules"] }),
  });

  const readMutation = useMutation({
    mutationFn: (id: number) => markAlertEventRead(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alertEvents"] }),
  });

  const createErrorMessage = createMutation.error
    ? isAxiosError<ApiErrorBody>(createMutation.error)
      ? (createMutation.error.response?.data?.detail ?? "Could not create rule.")
      : "Choose a portfolio first."
    : undefined;

  return (
    <div className="space-y-4">
      <div>
        <div className="text-sm font-medium mb-2" style={{ color: "var(--text-secondary)" }}>
          Recent alerts
        </div>
        {events.length === 0 ? (
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            No alerts yet.
          </div>
        ) : (
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {events.map((event) => (
              <button
                key={event.id}
                type="button"
                onClick={() => !event.is_read && readMutation.mutate(event.id)}
                className="w-full text-left text-xs px-2 py-1.5 rounded-md"
                style={{
                  background: event.is_read ? "transparent" : "var(--page-plane)",
                  color: event.is_read ? "var(--text-muted)" : "var(--text-primary)",
                }}
              >
                {event.message}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-2 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          New alert rule
        </div>

        <select
          value={portfolioId}
          onChange={(e) => setPortfolioId(e.target.value ? Number(e.target.value) : "")}
          className="w-full rounded-md px-2 py-1.5 text-sm"
          style={inputStyle}
        >
          <option value="">Select a saved portfolio…</option>
          {portfolios?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>

        <div className="flex gap-2">
          <select
            value={ruleType}
            onChange={(e) => setRuleType(e.target.value as AlertRuleType)}
            className="flex-1 rounded-md px-2 py-1.5 text-sm"
            style={inputStyle}
          >
            <option value="price_move">Price move</option>
            <option value="risk_metric">Risk metric</option>
          </select>
          <select
            value={direction}
            onChange={(e) => setDirection(e.target.value as AlertDirection)}
            className="rounded-md px-2 py-1.5 text-sm"
            style={inputStyle}
          >
            <option value="up">Up</option>
            <option value="down">Down</option>
          </select>
        </div>

        {ruleType === "price_move" ? (
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="TICKER"
            className="w-full rounded-md px-2 py-1.5 text-sm"
            style={inputStyle}
          />
        ) : (
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            className="w-full rounded-md px-2 py-1.5 text-sm"
            style={inputStyle}
          >
            {RISK_METRIC_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        )}

        <div className="flex items-center gap-2">
          <input
            type="number"
            step="0.1"
            min="0"
            value={thresholdPct}
            onChange={(e) => setThresholdPct(Number(e.target.value))}
            className="w-24 rounded-md px-2 py-1.5 text-sm"
            style={inputStyle}
          />
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            {ruleType === "price_move"
              ? "% move"
              : "metric value ×100 (e.g. 25 = 25% vol, or beta 1.20 = 120)"}
          </span>
        </div>

        {createErrorMessage && (
          <div className="text-xs" style={{ color: "var(--status-critical)" }}>
            {createErrorMessage}
          </div>
        )}

        <button
          type="button"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending || !portfolioId}
          className="w-full rounded-md py-1.5 text-sm font-medium text-white disabled:opacity-50"
          style={{ background: "var(--accent-blue)" }}
        >
          {createMutation.isPending ? "Adding…" : "Add rule"}
        </button>
      </div>

      {rules && rules.length > 0 && (
        <div className="space-y-1 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
          <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
            Your rules
          </div>
          {rules.map((rule) => (
            <div key={rule.id} className="flex items-center gap-2 text-xs">
              <span className="flex-1" style={{ color: "var(--text-primary)" }}>
                {rule.rule_type === "price_move" ? rule.ticker : rule.metric} {rule.direction}{" "}
                {rule.threshold_pct}
              </span>
              <button
                type="button"
                onClick={() => deleteMutation.mutate(rule.id)}
                className="px-2 py-1 rounded-md"
                style={{ color: "var(--status-critical)" }}
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
