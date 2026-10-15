import React from "react";
import { DashboardConnectionState } from "./dashboard.types";
import { WifiIcon, WifiOffIcon, RefreshIcon, AlertTriangleIcon, ClockIcon } from "./DashboardIcons";

interface ConnectionStatusProps {
  connectionState: DashboardConnectionState;
  lastSyncTimestamp?: string | null;
  isLoading?: boolean;
  onRefresh?: () => void;
}

export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({
  connectionState,
  lastSyncTimestamp,
  isLoading = false,
  onRefresh,
}) => {
  const getStatusConfig = () => {
    switch (connectionState) {
      case "connected":
        return {
          label: "Live Synced",
          badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800",
          dotClass: "bg-emerald-500",
          icon: <WifiIcon className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />,
          description: "Digital Twin is actively receiving updates from backend persistence.",
        };
      case "reconnecting":
        return {
          label: "Reconnecting",
          badgeClass: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800",
          dotClass: "bg-amber-500 animate-ping",
          icon: <RefreshIcon className="w-3.5 h-3.5 text-amber-600 animate-spin" />,
          description: "Attempting to re-establish connection to Digital Twin service.",
        };
      case "stale":
        return {
          label: "Data Stale",
          badgeClass: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950/40 dark:text-orange-300 dark:border-orange-800",
          dotClass: "bg-orange-500",
          icon: <ClockIcon className="w-3.5 h-3.5 text-orange-600 dark:text-orange-400" />,
          description: "Displayed records may not reflect recent scan confirmations.",
        };
      case "offline":
        return {
          label: "Backend Offline",
          badgeClass: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800",
          dotClass: "bg-rose-500",
          icon: <WifiOffIcon className="w-3.5 h-3.5 text-rose-500" />,
          description: "Unable to reach backend services. Showing the last successfully synced data when available.",
        };
      case "unavailable":
      default:
        return {
          label: "Service Unavailable",
          badgeClass: "bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
          dotClass: "bg-slate-400",
          icon: <AlertTriangleIcon className="w-3.5 h-3.5 text-slate-500" />,
          description: "Digital Twin service has not been initialized or registered.",
        };
    }
  };

  const config = getStatusConfig();

  const formatLastSync = (isoString?: string | null) => {
    if (!isoString) return "No sync recorded";
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Pill Badge */}
      <div
        className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-colors ${config.badgeClass}`}
        role="status"
        aria-live="polite"
        title={config.description}
      >
        <span className={`w-2 h-2 rounded-full ${config.dotClass}`} aria-hidden="true" />
        {config.icon}
        <span className="font-semibold">{config.label}</span>
      </div>

      {/* Last Sync Timestamp */}
      <div className="text-[11px] text-slate-500 dark:text-slate-400 flex items-center gap-1">
        <span className="text-slate-400 dark:text-slate-500">Last snapshot:</span>
        <span className="font-mono">{formatLastSync(lastSyncTimestamp)}</span>
      </div>

      {/* Manual Refresh Trigger */}
      {onRefresh && (
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="Refresh Digital Twin snapshot"
          title="Query backend for fresh Digital Twin state"
          className="p-1 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-800 disabled:opacity-40 transition-colors"
        >
          <RefreshIcon className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-emerald-600" : ""}`} />
        </button>
      )}
    </div>
  );
};
