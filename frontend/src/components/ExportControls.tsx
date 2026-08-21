import { useMutation } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { exportPortfolioReport } from "../api/client";
import type { ApiErrorBody } from "../api/client";

interface ExportControlsProps {
  portfolioId: number;
  benchmark: string;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ExportControls({ portfolioId, benchmark }: ExportControlsProps) {
  const exportMutation = useMutation({
    mutationFn: (format: "csv" | "pdf") =>
      exportPortfolioReport(portfolioId, format, benchmark, 3).then((blob) => ({ blob, format })),
    onSuccess: ({ blob, format }) => {
      downloadBlob(blob, `portfolio_${portfolioId}_report.${format}`);
    },
  });

  const errorMessage = exportMutation.error
    ? isAxiosError<ApiErrorBody>(exportMutation.error)
      ? (exportMutation.error.response?.data?.detail ?? "Export failed.")
      : "Something went wrong."
    : undefined;

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
        Export report
      </span>
      <button
        type="button"
        onClick={() => exportMutation.mutate("csv")}
        disabled={exportMutation.isPending}
        className="text-sm px-3 py-1.5 rounded-md disabled:opacity-50"
        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
      >
        CSV
      </button>
      <button
        type="button"
        onClick={() => exportMutation.mutate("pdf")}
        disabled={exportMutation.isPending}
        className="text-sm px-3 py-1.5 rounded-md disabled:opacity-50"
        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}
      >
        PDF
      </button>
      {errorMessage && (
        <span className="text-sm" style={{ color: "var(--status-critical)" }}>
          {errorMessage}
        </span>
      )}
    </div>
  );
}
