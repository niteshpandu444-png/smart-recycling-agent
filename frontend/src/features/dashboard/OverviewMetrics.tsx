import React from "react";
import { DashboardOverviewMetrics } from "./dashboard.types";

interface OverviewMetricsProps {
  metrics?: DashboardOverviewMetrics | null;
  isLoading?: boolean;
}

const panelClass = "border border-slate-200 bg-white p-4";
const labelClass = "text-xs font-medium text-slate-600";

export const OverviewMetrics: React.FC<OverviewMetricsProps> = ({ metrics, isLoading = false }) => {
  if (isLoading && !metrics) {
    return <div className="h-36 border border-slate-200 bg-white" aria-busy="true" aria-label="Loading recorded inventory" />;
  }

  if (!metrics) {
    return (
      <section aria-labelledby="overview-title" className={panelClass}>
        <h2 id="overview-title" className="text-sm font-semibold text-slate-900">Recorded inventory</h2>
        <p className="mt-2 text-sm text-slate-600">No snapshot data is available. Refresh to request the latest backend values.</p>
      </section>
    );
  }

  const cards = [
    { label: "Confirmed items", value: metrics.totalConfirmedItems.toLocaleString(), unit: "items", origin: "Recorded" },
    { label: "Destination bins", value: metrics.activeRoutesCount.toLocaleString(), unit: "bins", origin: "Recorded" },
    { label: "Pending verification", value: metrics.pendingVerificationCount == null ? "Unavailable" : metrics.pendingVerificationCount.toLocaleString(), unit: metrics.pendingVerificationCount == null ? "" : "items", origin: "Recorded" },
  ];

  return (
    <section aria-labelledby="overview-title" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="overview-title" className="text-sm font-semibold text-slate-900">Inventory overview</h2>
        <span className="text-xs text-slate-500">Values from the latest backend snapshot</span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {cards.map((card) => (
          <div key={card.label} className={panelClass}>
            <div className="flex items-center justify-between gap-2">
              <p className={labelClass}>{card.label}</p>
              <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{card.origin}</span>
            </div>
            <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-slate-950">
              {card.value}{card.unit && <span className="ml-2 text-sm font-normal text-slate-600">{card.unit}</span>}
            </p>
          </div>
        ))}
      </div>

      <div className={panelClass}>
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-slate-200 pb-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Category inventory</h3>
            <p className="mt-0.5 text-xs text-slate-500">Recorded quantities with calculated share of the reported category total.</p>
          </div>
          <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Share calculated from snapshot</span>
        </div>
        {metrics.categoryBreakdown.length === 0 ? (
          <p className="py-4 text-sm text-slate-600">No category inventory was reported in this snapshot.</p>
        ) : (
          <ul className="divide-y divide-slate-100" aria-label="Inventory by category">
            {metrics.categoryBreakdown.map((item) => (
              <li key={item.category} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 py-3 sm:grid-cols-[minmax(0,1fr)_9rem_5rem]">
                <span className="truncate text-sm font-medium text-slate-800" title={item.category}>{item.category}</span>
                <span className="font-mono text-sm tabular-nums text-slate-700">{item.count.toLocaleString()} {item.unit}</span>
                <span className="text-right font-mono text-xs tabular-nums text-slate-500">{item.percentageOfTotal.toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
};
