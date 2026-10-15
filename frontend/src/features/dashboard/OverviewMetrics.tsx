import React from "react";
import { DashboardOverviewMetrics, DashboardMaterialCategory } from "./dashboard.types";
import { BoxIcon, LayersIcon, ShieldAlertIcon, ActivityIcon, RecycleIcon, LeafIcon, SparklesIcon, AlertTriangleIcon } from "./DashboardIcons";

interface OverviewMetricsProps {
  metrics?: DashboardOverviewMetrics | null;
  isLoading?: boolean;
}

const CATEGORY_METRIC_CONFIG: Record<
  DashboardMaterialCategory,
  { label: string; textClass: string; bgClass: string; borderClass: string; icon: React.ReactNode }
> = {
  recyclable: {
    label: "Recyclable",
    textClass: "text-emerald-700 dark:text-emerald-300",
    bgClass: "bg-emerald-50 dark:bg-emerald-950/40",
    borderClass: "border-emerald-200 dark:border-emerald-800",
    icon: <RecycleIcon className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />,
  },
  reusable: {
    label: "Reusable",
    textClass: "text-sky-700 dark:text-sky-300",
    bgClass: "bg-sky-50 dark:bg-sky-950/40",
    borderClass: "border-sky-200 dark:border-sky-800",
    icon: <SparklesIcon className="w-4 h-4 text-sky-600 dark:text-sky-400" />,
  },
  biodegradable: {
    label: "Biodegradable",
    textClass: "text-amber-700 dark:text-amber-300",
    bgClass: "bg-amber-50 dark:bg-amber-950/40",
    borderClass: "border-amber-200 dark:border-amber-800",
    icon: <LeafIcon className="w-4 h-4 text-amber-600 dark:text-amber-400" />,
  },
  hazardous: {
    label: "Hazardous",
    textClass: "text-rose-700 dark:text-rose-300",
    bgClass: "bg-rose-50 dark:bg-rose-950/40",
    borderClass: "border-rose-200 dark:border-rose-800",
    icon: <AlertTriangleIcon className="w-4 h-4 text-rose-600 dark:text-rose-400" />,
  },
  unknown: {
    label: "Uncategorized",
    textClass: "text-slate-700 dark:text-slate-300",
    bgClass: "bg-slate-50 dark:bg-slate-900/60",
    borderClass: "border-slate-200 dark:border-slate-800",
    icon: <BoxIcon className="w-4 h-4 text-slate-500" />,
  },
};

export const OverviewMetrics: React.FC<OverviewMetricsProps> = ({ metrics, isLoading = false }) => {
  if (isLoading && !metrics) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse" aria-busy="true">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-28 bg-slate-200 dark:bg-slate-800/80 rounded-2xl p-4 border border-slate-200 dark:border-slate-800" />
        ))}
      </div>
    );
  }

  const totalItems = metrics?.totalConfirmedItems ?? 0;
  const activeRoutes = metrics?.activeRoutesCount ?? 0;
  const pendingCount = metrics?.pendingVerificationCount ?? 0;
  const breakdown = metrics?.categoryBreakdown ?? [];

  return (
    <section aria-labelledby="overview-metrics-title" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 id="overview-metrics-title" className="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Digital Twin Material Telemetry
        </h2>
        <span className="text-[11px] px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700 font-mono">
          OBSERVED & CALCULATED METRICS
        </span>
      </div>

      {/* Primary KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Card 1: Total Confirmed Items (Observed) */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm relative overflow-hidden">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[10px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
                  OBSERVED
                </span>
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Total Processed
                </span>
              </div>
              <p className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
                {totalItems.toLocaleString()}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400">
              <BoxIcon className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            Confirmed items committed to Digital Twin persistence.
          </p>
        </div>

        {/* Card 2: Active Virtual Routes (Observed) */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm relative overflow-hidden">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[10px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300">
                  OBSERVED
                </span>
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Active Routes / Bins
                </span>
              </div>
              <p className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
                {activeRoutes}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400">
              <LayersIcon className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            Designated facility bins registered in material flow.
          </p>
        </div>

        {/* Card 3: Pending Verification & Risk (Observed) */}
        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm relative overflow-hidden">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[10px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300">
                  OBSERVED
                </span>
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Needs Review
                </span>
              </div>
              <p className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
                {pendingCount}
              </p>
            </div>
            <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/50 text-amber-600 dark:text-amber-400">
              <ShieldAlertIcon className="w-5 h-5" />
            </div>
          </div>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            {pendingCount === 0
              ? "All classified scans confirmed or verified."
              : "Items flagged for manual verification or high ambiguity."}
          </p>
        </div>
      </div>

      {/* Category Distribution Bar (Calculated) */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <ActivityIcon className="w-4 h-4 text-slate-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
              Material Distribution by Category
            </h3>
          </div>
          <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
            CALCULATED RATIO
          </span>
        </div>

        {breakdown.length === 0 ? (
          <p className="text-xs text-slate-400 italic py-2">
            No category distribution available yet. As items are scanned and confirmed, category percentages will render here.
          </p>
        ) : (
          <div>
            {/* Visual stacked percentage bar */}
            <div className="w-full h-3 rounded-full bg-slate-100 dark:bg-slate-800 flex overflow-hidden mb-4 border border-slate-200/50 dark:border-slate-700/50">
              {breakdown.map((item) => {
                const config = CATEGORY_METRIC_CONFIG[item.category] || CATEGORY_METRIC_CONFIG.unknown;
                const widthPercent = Math.max(0, Math.min(100, item.percentageOfTotal));
                if (widthPercent === 0) return null;
                return (
                  <div
                    key={item.category}
                    style={{ width: `${widthPercent}%` }}
                    className={`${config.bgClass} transition-all duration-300`}
                    title={`${config.label}: ${item.count} ${item.unit} (${widthPercent.toFixed(1)}%)`}
                    aria-label={`${config.label}: ${widthPercent.toFixed(1)}%`}
                  />
                );
              })}
            </div>

            {/* Category breakdown pill chips */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {breakdown.map((item) => {
                const config = CATEGORY_METRIC_CONFIG[item.category] || CATEGORY_METRIC_CONFIG.unknown;
                return (
                  <div
                    key={item.category}
                    className={`flex items-center gap-2 p-2 rounded-xl border ${config.borderClass} ${config.bgClass}`}
                  >
                    <div className="shrink-0">{config.icon}</div>
                    <div className="min-w-0 flex-1">
                      <p className={`text-xs font-semibold truncate ${config.textClass}`}>
                        {config.label}
                      </p>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400 font-mono">
                        {item.count} {item.unit} ({item.percentageOfTotal.toFixed(1)}%)
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  );
};
