import React from "react";
import { DashboardConnectionState, DashboardRestApiState } from "./dashboard.types";
import { WifiIcon, WifiOffIcon, RefreshIcon, AlertTriangleIcon, ClockIcon } from "./DashboardIcons";

interface ConnectionStatusProps {
  connectionState: DashboardConnectionState;
  restApiState: DashboardRestApiState;
  lastSyncTimestamp?: string | null;
  isLoading?: boolean;
  onRefresh?: () => void;
}

const STATUS: Record<DashboardConnectionState, { label: string; detail: string; className: string; icon: React.ReactNode }> = {
  connected: { label: "Connected", detail: "Live connection open", className: "border-emerald-200 bg-emerald-50 text-emerald-800", icon: <WifiIcon className="h-4 w-4" /> },
  reconnecting: { label: "Reconnecting", detail: "Live connection retrying", className: "border-amber-200 bg-amber-50 text-amber-800", icon: <RefreshIcon className="h-4 w-4" /> },
  stale: { label: "Data may be stale", detail: "Latest request did not complete", className: "border-amber-200 bg-amber-50 text-amber-800", icon: <ClockIcon className="h-4 w-4" /> },
  offline: { label: "Backend offline", detail: "No successful backend response", className: "border-rose-200 bg-rose-50 text-rose-800", icon: <WifiOffIcon className="h-4 w-4" /> },
  unavailable: { label: "Unavailable", detail: "Service state unavailable", className: "border-slate-300 bg-slate-100 text-slate-700", icon: <AlertTriangleIcon className="h-4 w-4" /> },
};

function formatLastSync(value?: string | null): string {
  if (!value) return "No successful refresh recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "medium" });
}

export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({ connectionState, restApiState, lastSyncTimestamp, isLoading = false, onRefresh }) => {
  const status = STATUS[connectionState];
  const restStatus = restApiState === "available"
    ? { label: "REST API available", className: "border-emerald-200 bg-emerald-50 text-emerald-800" }
    : restApiState === "unavailable"
    ? { label: "REST API unavailable", className: "border-rose-200 bg-rose-50 text-rose-800" }
    : { label: "Checking REST API", className: "border-slate-300 bg-slate-100 text-slate-700" };
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 md:justify-end">
      <div className={`inline-flex items-center gap-2 border px-2.5 py-1.5 text-xs font-medium ${restStatus.className}`} role="status" aria-live="polite">
        <span>{restStatus.label}</span>
      </div>
      <div className={`inline-flex items-center gap-2 border px-2.5 py-1.5 text-xs font-medium ${status.className}`} role="status" aria-live="polite">
        {status.icon}
        <span>{status.label}</span>
        <span className="hidden border-l border-current/20 pl-2 font-normal sm:inline">{status.detail}</span>
      </div>
      <div className="flex items-center gap-1.5 text-xs text-slate-600">
        <span>Last successful refresh</span>
        <time className="font-mono text-slate-800" dateTime={lastSyncTimestamp ?? undefined}>{formatLastSync(lastSyncTimestamp)}</time>
      </div>
      {onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          className="inline-flex min-h-9 items-center gap-2 border border-slate-300 bg-white px-3 text-xs font-medium text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
          aria-label="Refresh dashboard data"
        >
          <RefreshIcon className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      )}
    </div>
  );
};
