import React from "react";
import { DashboardBin, DashboardMaterialCategory, BinOperationalStatus } from "./dashboard.types";
import { RecycleIcon, SparklesIcon, LeafIcon, AlertTriangleIcon, BoxIcon, ShieldAlertIcon, InfoIcon } from "./DashboardIcons";

interface VirtualBinGridProps {
  bins?: DashboardBin[];
  isLoading?: boolean;
}

const CATEGORY_BIN_THEMES: Record<
  DashboardMaterialCategory,
  { label: string; borderClass: string; icon: React.ReactNode; badgeClass: string }
> = {
  recyclable: {
    label: "Recyclable",
    borderClass: "border-emerald-300 dark:border-emerald-800",
    icon: <RecycleIcon className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />,
    badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800",
  },
  reusable: {
    label: "Reusable",
    borderClass: "border-sky-300 dark:border-sky-800",
    icon: <SparklesIcon className="w-4 h-4 text-sky-600 dark:text-sky-400" />,
    badgeClass: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-800",
  },
  biodegradable: {
    label: "Biodegradable",
    borderClass: "border-amber-300 dark:border-amber-800",
    icon: <LeafIcon className="w-4 h-4 text-amber-600 dark:text-amber-400" />,
    badgeClass: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800",
  },
  hazardous: {
    label: "Hazardous",
    borderClass: "border-rose-300 dark:border-rose-800",
    icon: <AlertTriangleIcon className="w-4 h-4 text-rose-600 dark:text-rose-400" />,
    badgeClass: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800",
  },
  unknown: {
    label: "Uncategorized",
    borderClass: "border-slate-300 dark:border-slate-700",
    icon: <BoxIcon className="w-4 h-4 text-slate-500" />,
    badgeClass: "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
  },
};

const STATUS_CONFIG: Record<
  BinOperationalStatus,
  { label: string; badgeClass: string; barColorClass: string }
> = {
  normal: {
    label: "Normal",
    badgeClass: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    barColorClass: "bg-emerald-500",
  },
  warning: {
    label: "Warning",
    badgeClass: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    barColorClass: "bg-amber-500",
  },
  critical: {
    label: "Critical",
    badgeClass: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
    barColorClass: "bg-rose-600",
  },
  maintenance: {
    label: "Maintenance",
    badgeClass: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300",
    barColorClass: "bg-slate-500",
  },
  unknown: {
    label: "Status Unreported",
    badgeClass: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300",
    barColorClass: "bg-slate-400",
  },
};

/**
 * Validates whether capacity and inventory quantities are compatible and calculates percentage honestly.
 */
function calculateSafeOccupancy(
  currentInventory: number,
  capacity?: number | null,
  reportedPercentage?: number | null
): { percent: number | null; isValid: boolean; isOverflow: boolean; explanation: string } {
  // If backend provided an explicit occupancy percentage, accept only finite numbers >= 0
  if (
    typeof reportedPercentage === "number" &&
    Number.isFinite(reportedPercentage) &&
    reportedPercentage >= 0
  ) {
    return {
      percent: reportedPercentage,
      isValid: true,
      isOverflow: reportedPercentage > 100,
      explanation: reportedPercentage > 100 ? "Bin exceeded maximum capacity" : "Backend-reported occupancy",
    };
  }

  // When reported percentage is missing or invalid, fall back to calculating from inventory and capacity
  // Check if configured capacity is valid (must be a finite number > 0)
  if (
    capacity === null ||
    capacity === undefined ||
    typeof capacity !== "number" ||
    !Number.isFinite(capacity) ||
    capacity <= 0
  ) {
    return {
      percent: null,
      isValid: false,
      isOverflow: false,
      explanation: "Capacity unconfigured. Showing recorded inventory only.",
    };
  }

  if (
    typeof currentInventory !== "number" ||
    !Number.isFinite(currentInventory) ||
    currentInventory < 0
  ) {
    return {
      percent: null,
      isValid: false,
      isOverflow: false,
      explanation: "Inventory measurement invalid.",
    };
  }

  const calculated = (currentInventory / capacity) * 100;
  return {
    percent: calculated,
    isValid: true,
    isOverflow: calculated > 100,
    explanation: calculated > 100 ? "Overflow detected (>100%)" : `${calculated.toFixed(1)}% occupied`,
  };
}

export const VirtualBinGrid: React.FC<VirtualBinGridProps> = ({ bins = [], isLoading = false }) => {
  if (isLoading && bins.length === 0) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 animate-pulse" aria-busy="true">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-40 border border-slate-200 bg-white" />
        ))}
      </div>
    );
  }

  if (bins.length === 0) {
    return (
      <div className="border border-slate-200 bg-white p-6">
        <BoxIcon className="w-10 h-10 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
        <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">
          No destination bins recorded
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm mx-auto mt-1">
          The latest backend snapshot contains no destination bin records.
        </p>
      </div>
    );
  }

  return (
    <section aria-labelledby="virtual-bins-title" className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 id="virtual-bins-title" className="text-sm font-semibold text-slate-900">
            Virtual bin state
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">{bins.length} destination bins recorded in the backend snapshot</p>
        </div>
        <span className="text-[11px] font-mono uppercase px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
          VIRTUAL TWIN MODEL
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {bins.map((bin) => {
          const theme = CATEGORY_BIN_THEMES[bin.category] || {
            ...CATEGORY_BIN_THEMES.unknown,
          };
          const statusConfig = STATUS_CONFIG[bin.status] || STATUS_CONFIG.unknown;
          const occupancy = calculateSafeOccupancy(bin.currentInventory, bin.capacity, bin.occupancyPercentage);

          return (
            <div
              key={bin.id}
              className="flex flex-col justify-between border border-slate-200 bg-white p-4"
            >
              <div>
                {/* Header: Name, Category, Status */}
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="border border-slate-200 bg-slate-50 p-2 shrink-0">
                      {theme.icon}
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate" title={bin.name}>
                        {bin.name}
                      </h3>
                      <p className="text-[11px] font-mono text-slate-400 truncate">
                        ID: {bin.id}
                      </p>
                    </div>
                  </div>

                  {/* Status Pill */}
                  <span className={`border px-2 py-1 text-[10px] font-medium uppercase tracking-wide shrink-0 ${statusConfig.badgeClass}`}>
                    {statusConfig.label}
                  </span>
                </div>

                {/* Category Badge */}
                <div className="mb-4">
                  <span className={`inline-flex items-center gap-1 border px-2 py-1 text-[11px] font-medium ${theme.badgeClass}`}>
                      {bin.category}
                  </span>
                </div>

                {/* Capacity Visual Meter */}
                <div className="space-y-1.5 mb-4">
                  <div className="flex justify-between items-baseline text-xs">
                    <span className="text-slate-500 dark:text-slate-400 font-medium">
                      Fill level:
                    </span>
                    <span className="font-mono font-bold text-slate-900 dark:text-slate-100">
                      {occupancy.isValid && occupancy.percent !== null ? (
                        <>
                          <span className={occupancy.isOverflow ? "text-rose-600 font-black" : ""}>
                            {occupancy.percent.toFixed(1)}%
                          </span>
                        </>
                      ) : (
                        <span className="text-slate-500 font-normal">Unavailable</span>
                      )}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    {typeof bin.occupancyPercentage === "number" && Number.isFinite(bin.occupancyPercentage)
                      ? "Occupancy reported by backend"
                      : occupancy.isValid
                        ? "Occupancy calculated from inventory and capacity"
                        : "Occupancy unavailable: capacity not configured"}
                  </p>

                  {/* Fill progress bar */}
                  <div className="w-full h-3 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden relative border border-slate-200/60 dark:border-slate-700/60">
                    {occupancy.isValid && occupancy.percent !== null ? (
                      <div
                        style={{ width: `${Math.min(100, Math.max(0, occupancy.percent))}%` }}
                        className={`h-full ${statusConfig.barColorClass} transition-all duration-300`}
                        role="progressbar"
                        aria-valuenow={Math.round(occupancy.percent)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`${bin.name} fill level: ${occupancy.percent.toFixed(1)}%`}
                      />
                    ) : (
                      <div className="w-full h-full bg-slate-200/50 dark:bg-slate-700/30 flex items-center justify-center">
                        <span className="text-[9px] text-slate-400">No capacity limit set</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Inventory vs Capacity Figures */}
                <div className="grid grid-cols-2 gap-2 border border-slate-200 bg-slate-50 p-3 text-xs">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">
                      Current Volume
                    </span>
                    <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                      {bin.currentInventory} {bin.inventoryUnit}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">
                      Configured Limit
                    </span>
                    <span className="font-mono text-slate-600 dark:text-slate-300">
                      {bin.capacity && bin.capacity > 0 ? `${bin.capacity} ${bin.inventoryUnit}` : "Unavailable"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Footer: Contamination Indicator & Service Warning */}
              <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 text-[11px] flex items-center justify-between">
                {typeof bin.contaminationRisk === "number" && Number.isFinite(bin.contaminationRisk) && bin.contaminationRisk >= 0 ? (
                  <div className="flex items-center gap-1 text-slate-600" title="Backend-reported contamination risk">
                    <ShieldAlertIcon className="w-3.5 h-3.5" />
                    <span>Contamination risk: {(bin.contaminationRisk * 100).toFixed(0)}% · reported</span>
                  </div>
                ) : (
                  <span className="text-slate-500">Contamination risk: Unavailable</span>
                )}

                {bin.needsService && (
                  <span className="font-bold text-rose-600 dark:text-rose-400 flex items-center gap-1">
                    <InfoIcon className="w-3 h-3" /> Pickup Needed
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};
