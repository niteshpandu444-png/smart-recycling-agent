import React from "react";
import { DashboardOverviewMetrics, DashboardMaterialCategory } from "./dashboard.types";
import { LayersIcon, BoxIcon, ShieldAlertIcon, EyeIcon, ScanIcon } from "./DashboardIcons";

interface BatchActivityPanelProps {
  metrics?: DashboardOverviewMetrics | null;
  isLoading?: boolean;
}

const CATEGORY_LABELS: Record<DashboardMaterialCategory, string> = {
  recyclable: "Recyclable",
  reusable: "Reusable",
  biodegradable: "Biodegradable",
  hazardous: "Hazardous",
  unknown: "Uncategorized",
};

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "unknown time";
  return parsed.toLocaleString();
}

/**
 * Mixed-waste batch activity.
 *
 * Every number here counts *detected* items unless it is explicitly labelled as
 * confirmed. Items awaiting review are reported as pending work, and a detected
 * item is never presented as inventory.
 */
export const BatchActivityPanel: React.FC<BatchActivityPanelProps> = ({
  metrics,
  isLoading = false,
}) => {
  if (isLoading && !metrics) {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm animate-pulse" aria-busy="true">
        <div className="h-5 w-56 bg-slate-200 dark:bg-slate-800 rounded mb-4" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((index) => (
            <div key={index} className="h-20 bg-slate-100 dark:bg-slate-800/70 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  const scenesScanned = metrics?.batchScanCount ?? 0;
  const itemsDetected = metrics?.detectedItemCount ?? 0;
  const awaitingReview = metrics?.needsReviewScanCount ?? 0;
  const confirmedFromBatches = metrics?.confirmedFromBatchCount ?? 0;
  const detectedBreakdown = metrics?.detectedCategoryBreakdown ?? [];
  const recentBatches = metrics?.recentBatches ?? [];

  const tiles = [
    {
      label: "Mixed scenes scanned",
      value: scenesScanned,
      caption: "Images analysed for multiple items",
      icon: <ScanIcon className="w-4 h-4 text-brand-600 dark:text-brand-400" />,
      tone: "text-brand-700 dark:text-brand-300",
    },
    {
      label: "Items detected",
      value: itemsDetected,
      caption: "Detected objects, not inventory",
      icon: <LayersIcon className="w-4 h-4 text-slate-500" />,
      tone: "text-slate-700 dark:text-slate-200",
    },
    {
      label: "Awaiting review",
      value: awaitingReview,
      caption: "Flagged by a stored review reason",
      icon: <ShieldAlertIcon className="w-4 h-4 text-amber-600 dark:text-amber-400" />,
      tone: "text-amber-700 dark:text-amber-300",
    },
    {
      label: "Confirmed from batches",
      value: confirmedFromBatches,
      caption: "Recorded into inventory by a user",
      icon: <BoxIcon className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />,
      tone: "text-emerald-700 dark:text-emerald-300",
    },
  ];

  return (
    <section
      aria-labelledby="batch-activity-title"
      className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-50 dark:bg-brand-950/60">
            <LayersIcon className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
          </span>
          <h2
            id="batch-activity-title"
            className="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400"
          >
            Mixed-Waste Batch Activity
          </h2>
        </div>
        <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 border border-slate-200 dark:border-slate-700">
          DETECTED ≠ CONFIRMED
        </span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {tiles.map((tile) => (
          <div
            key={tile.label}
            className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 p-3"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {tile.label}
              </span>
              {tile.icon}
            </div>
            <p className={`text-2xl font-extrabold tracking-tight ${tile.tone}`}>
              {tile.value.toLocaleString()}
            </p>
            <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">{tile.caption}</p>
          </div>
        ))}
      </div>

      {/* Detected items grouped by category */}
      {detectedBreakdown.length > 0 && (
        <div className="mb-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-2">
            Detected items by material group
          </h3>
          <div className="flex flex-wrap gap-2">
            {detectedBreakdown.map((entry) => (
              <span
                key={entry.category}
                className="text-[11px] px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700"
              >
                {CATEGORY_LABELS[entry.category] ?? entry.category}: {entry.count}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Recent batch list */}
      {recentBatches.length === 0 ? (
        <p className="text-xs text-slate-400 dark:text-slate-500 italic">
          No mixed-scene scans recorded yet. Scan a scene with the Mixed Scene mode and detected
          items will appear here; they only count as inventory once you confirm them.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[11px]">
            <caption className="sr-only">
              Recent mixed-waste scene scans with detected, confirmed, and pending review counts
            </caption>
            <thead>
              <tr className="text-slate-400 dark:text-slate-500 uppercase text-[10px] tracking-wide">
                <th scope="col" className="py-1.5 pr-3 font-semibold">
                  Scene
                </th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">
                  Detected
                </th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">
                  Confirmed
                </th>
                <th scope="col" className="py-1.5 pr-3 font-semibold">
                  Pending review
                </th>
                <th scope="col" className="py-1.5 font-semibold">
                  Recorded at
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {recentBatches.map((batch) => (
                <tr key={batch.batchId} className="text-slate-600 dark:text-slate-300">
                  <td className="py-2 pr-3 font-mono text-[10px] text-slate-500 dark:text-slate-400">
                    {batch.batchId.slice(0, 8)}
                  </td>
                  <td className="py-2 pr-3 font-semibold">{batch.detectionCount}</td>
                  <td className="py-2 pr-3">{batch.confirmedCount}</td>
                  <td className="py-2 pr-3">
                    <span className="flex items-center gap-1">
                      <EyeIcon className="w-3 h-3 text-amber-500" />
                      {batch.pendingReviewCount}
                    </span>
                  </td>
                  <td className="py-2 text-slate-500 dark:text-slate-400">
                    {formatTimestamp(batch.createdAt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-3 text-[10px] text-slate-400 dark:text-slate-500 leading-relaxed">
        Detected items are pending records. Only items confirmed in the scanner reach inventory, and
        reviews are requested for documented reasons such as low score, an unsupported material
        class, or conflicting labels for the same region.
      </p>
    </section>
  );
};
