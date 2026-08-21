import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPortfolio,
  deletePortfolio,
  getPortfolio,
  listPortfolios,
  updatePortfolio,
} from "../api/client";
import type { HoldingInput, PortfolioOut } from "../api/client";

export interface ActivePortfolio {
  id: number;
  name: string;
}

interface SavedPortfoliosProps {
  activePortfolio: ActivePortfolio | null;
  onActivePortfolioChange: (portfolio: ActivePortfolio | null) => void;
  currentHoldings: HoldingInput[];
  onLoadPortfolio: (holdings: HoldingInput[]) => void;
}

export function SavedPortfolios({
  activePortfolio,
  onActivePortfolioChange,
  currentHoldings,
  onLoadPortfolio,
}: SavedPortfoliosProps) {
  const queryClient = useQueryClient();
  const [draftName, setDraftName] = useState("");

  const { data: portfolios, isLoading } = useQuery({
    queryKey: ["portfolios"],
    queryFn: listPortfolios,
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      createPortfolio({ name: draftName || "Untitled portfolio", holdings: currentHoldings }),
    onSuccess: (portfolio: PortfolioOut) => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      onActivePortfolioChange({ id: portfolio.id, name: portfolio.name });
      setDraftName("");
    },
  });

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!activePortfolio) throw new Error("No active portfolio");
      return updatePortfolio(activePortfolio.id, {
        name: activePortfolio.name,
        holdings: currentHoldings,
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portfolios"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deletePortfolio(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ["portfolios"] });
      if (activePortfolio?.id === id) onActivePortfolioChange(null);
    },
  });

  async function handleLoad(id: number, portfolioName: string) {
    const portfolio = await getPortfolio(id);
    onLoadPortfolio(portfolio.holdings.map((h) => ({ ticker: h.ticker, weight: h.weight ?? 0 })));
    onActivePortfolioChange({ id, name: portfolioName });
  }

  const inputStyle = {
    background: "var(--page-plane)",
    border: "1px solid var(--border)",
    color: "var(--text-primary)",
  };

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ background: "var(--surface-1)", border: "1px solid var(--border)" }}
    >
      <div className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
        Saved portfolios
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={activePortfolio ? activePortfolio.name : draftName}
          onChange={(e) =>
            activePortfolio
              ? onActivePortfolioChange({ ...activePortfolio, name: e.target.value })
              : setDraftName(e.target.value)
          }
          placeholder="Portfolio name"
          className="flex-1 rounded-md px-2 py-1.5 text-sm"
          style={inputStyle}
        />
        {activePortfolio ? (
          <button
            type="button"
            onClick={() => updateMutation.mutate()}
            disabled={updateMutation.isPending}
            className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
            style={{ background: "var(--accent-blue)" }}
          >
            {updateMutation.isPending ? "Saving…" : "Update"}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || currentHoldings.length === 0}
            className="text-sm px-3 py-1.5 rounded-md text-white disabled:opacity-50"
            style={{ background: "var(--accent-blue)" }}
          >
            {saveMutation.isPending ? "Saving…" : "Save as new"}
          </button>
        )}
        {activePortfolio && (
          <button
            type="button"
            onClick={() => onActivePortfolioChange(null)}
            className="text-sm px-3 py-1.5 rounded-md"
            style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
          >
            New
          </button>
        )}
      </div>

      {isLoading && (
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          Loading…
        </div>
      )}

      {portfolios && portfolios.length > 0 && (
        <div className="space-y-1">
          {portfolios.map((p) => (
            <div key={p.id} className="flex items-center gap-2 text-sm">
              <span
                className="flex-1"
                style={{
                  color: activePortfolio?.id === p.id ? "var(--accent-blue)" : "var(--text-primary)",
                }}
              >
                {p.name}
              </span>
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                {p.holding_count} holdings
              </span>
              <button
                type="button"
                onClick={() => handleLoad(p.id, p.name)}
                className="text-xs px-2 py-1 rounded-md"
                style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
              >
                Load
              </button>
              <button
                type="button"
                onClick={() => deleteMutation.mutate(p.id)}
                className="text-xs px-2 py-1 rounded-md"
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
