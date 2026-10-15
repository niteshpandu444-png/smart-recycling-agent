import React from "react";
import { MaterialFlowNode, DashboardMaterialCategory } from "./dashboard.types";
import { RecycleIcon, SparklesIcon, LeafIcon, AlertTriangleIcon, BoxIcon, ArrowRightIcon, ActivityIcon } from "./DashboardIcons";

interface MaterialFlowProps {
  flows?: MaterialFlowNode[];
  isLoading?: boolean;
}

const CATEGORY_FLOW_THEMES: Record<
  DashboardMaterialCategory,
  { label: string; stroke: string; fill: string; textClass: string; bgClass: string; borderClass: string; icon: React.ReactNode }
> = {
  recyclable: {
    label: "Recyclable Stream",
    stroke: "#10b981", // emerald-500
    fill: "rgba(16, 185, 129, 0.15)",
    textClass: "text-emerald-700 dark:text-emerald-300",
    bgClass: "bg-emerald-50 dark:bg-emerald-950/40",
    borderClass: "border-emerald-300 dark:border-emerald-800",
    icon: <RecycleIcon className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />,
  },
  reusable: {
    label: "Reusable Stream",
    stroke: "#0284c7", // sky-600
    fill: "rgba(2, 132, 199, 0.15)",
    textClass: "text-sky-700 dark:text-sky-300",
    bgClass: "bg-sky-50 dark:bg-sky-950/40",
    borderClass: "border-sky-300 dark:border-sky-800",
    icon: <SparklesIcon className="w-4 h-4 text-sky-600 dark:text-sky-400" />,
  },
  biodegradable: {
    label: "Biodegradable Stream",
    stroke: "#d97706", // amber-600
    fill: "rgba(217, 119, 6, 0.15)",
    textClass: "text-amber-700 dark:text-amber-300",
    bgClass: "bg-amber-50 dark:bg-amber-950/40",
    borderClass: "border-amber-300 dark:border-amber-800",
    icon: <LeafIcon className="w-4 h-4 text-amber-600 dark:text-amber-400" />,
  },
  hazardous: {
    label: "Hazardous Stream",
    stroke: "#e11d48", // rose-600
    fill: "rgba(225, 29, 72, 0.15)",
    textClass: "text-rose-700 dark:text-rose-300",
    bgClass: "bg-rose-50 dark:bg-rose-950/40",
    borderClass: "border-rose-300 dark:border-rose-800",
    icon: <AlertTriangleIcon className="w-4 h-4 text-rose-600 dark:text-rose-400" />,
  },
  unknown: {
    label: "Unsorted / Awaiting Review",
    stroke: "#64748b", // slate-500
    fill: "rgba(100, 116, 139, 0.15)",
    textClass: "text-slate-700 dark:text-slate-300",
    bgClass: "bg-slate-50 dark:bg-slate-900/60",
    borderClass: "border-slate-300 dark:border-slate-700",
    icon: <BoxIcon className="w-4 h-4 text-slate-500" />,
  },
};

export const MaterialFlow: React.FC<MaterialFlowProps> = ({ flows = [], isLoading = false }) => {
  if (isLoading && flows.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 animate-pulse h-64" aria-busy="true" />
    );
  }

  const totalVolume = flows.reduce((acc, f) => acc + (f.quantity || 0), 0);

  return (
    <section aria-labelledby="material-flow-title" className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ActivityIcon className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          <h2 id="material-flow-title" className="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Material Routing & Flow Dynamics
          </h2>
        </div>
        <span className="text-[11px] font-mono uppercase px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
          DERIVED FROM VERIFIED DATA
        </span>
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm">
        {flows.length === 0 ? (
          <div className="py-10 text-center">
            <BoxIcon className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
            <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300">
              No Material Movement Recorded Yet
            </h3>
            <p className="text-[11px] text-slate-400 max-w-sm mx-auto mt-1">
              Material flow vectors represent physical routing from mobile scanning confirmation into destination bins. When scans are recorded, active streams will display here.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Flow Stage Headers */}
            <div className="hidden md:grid grid-cols-3 gap-4 text-center pb-2 border-b border-slate-100 dark:border-slate-800 text-xs font-bold text-slate-500 uppercase tracking-wider">
              <div>Stage 1: Intake & Scan</div>
              <div>Stage 2: Verification & Stream</div>
              <div>Stage 3: Destination Storage</div>
            </div>

            {/* Visual Stream Lanes */}
            <div className="space-y-3">
              {flows.map((flow) => {
                const theme = CATEGORY_FLOW_THEMES[flow.category] || CATEGORY_FLOW_THEMES.unknown;
                const sharePercent =
                  flow.flowSharePercentage !== undefined
                    ? flow.flowSharePercentage
                    : totalVolume > 0
                    ? (flow.quantity / totalVolume) * 100
                    : 0;

                return (
                  <div
                    key={flow.id}
                    className={`rounded-xl p-3 border ${theme.borderClass} ${theme.bgClass} transition-all`}
                  >
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                      {/* Left: Source / Stream info */}
                      <div className="flex items-center gap-2.5 min-w-[200px]">
                        <div className="p-2 rounded-lg bg-white dark:bg-slate-800 shadow-xs shrink-0">
                          {theme.icon}
                        </div>
                        <div>
                          <p className={`text-xs font-bold ${theme.textClass}`}>
                            {flow.label}
                          </p>
                          <span className="text-[10px] uppercase font-mono px-1 rounded bg-white/70 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                            {flow.dataOrigin.toUpperCase()}
                          </span>
                        </div>
                      </div>

                      {/* Middle: Vector connector (desktop) or arrow (mobile) */}
                      <div className="flex-1 flex items-center gap-2">
                        <div className="hidden md:flex flex-1 items-center gap-1">
                          <div className="h-0.5 flex-1 rounded-full bg-slate-200 dark:bg-slate-700 relative overflow-hidden">
                            <div
                              style={{ width: `${Math.min(100, Math.max(10, sharePercent))}%` }}
                              className="h-full bg-slate-400 dark:bg-slate-500 rounded-full"
                            />
                          </div>
                          <ArrowRightIcon className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        </div>

                        {/* Quantity and share badge */}
                        <div className="shrink-0 px-2.5 py-1 rounded-md bg-white/80 dark:bg-slate-800/80 border border-slate-200/50 dark:border-slate-700/50 text-right min-w-[110px]">
                          <span className="font-mono text-xs font-bold text-slate-800 dark:text-slate-100 block">
                            {flow.quantity} {flow.unit}
                          </span>
                          <span className="text-[10px] text-slate-500 font-mono">
                            {sharePercent.toFixed(1)}% of flow
                          </span>
                        </div>
                      </div>

                      {/* Right: Target Bin */}
                      <div className="md:min-w-[180px] md:text-right flex items-center md:justify-end gap-1.5 text-xs">
                        <span className="text-slate-500 text-[11px]">Routed to:</span>
                        <span className="font-semibold text-slate-800 dark:text-slate-200 font-mono">
                          {flow.targetBinName || flow.targetBinId || "Designated Bin"}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Note on Data Grounding */}
            <p className="text-[10px] text-slate-400 dark:text-slate-500 text-center pt-2">
              Note: Flow volumes are derived exclusively from verified transaction logs. Historical throughput is not conflated with momentary bin fullness.
            </p>
          </div>
        )}
      </div>
    </section>
  );
};
