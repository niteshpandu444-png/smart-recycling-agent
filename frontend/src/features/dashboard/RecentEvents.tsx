import React from "react";
import { DashboardEvent, DashboardMaterialCategory } from "./dashboard.types";
import { RecycleIcon, SparklesIcon, LeafIcon, AlertTriangleIcon, BoxIcon, ClockIcon, CheckCircle2Icon } from "./DashboardIcons";

interface RecentEventsProps {
  events?: DashboardEvent[];
  isLoading?: boolean;
}

const CATEGORY_EVENT_BADGES: Record<
  DashboardMaterialCategory,
  { label: string; badgeClass: string; icon: React.ReactNode }
> = {
  recyclable: {
    label: "Recyclable",
    badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800",
    icon: <RecycleIcon className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />,
  },
  reusable: {
    label: "Reusable",
    badgeClass: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-800",
    icon: <SparklesIcon className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />,
  },
  biodegradable: {
    label: "Biodegradable",
    badgeClass: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800",
    icon: <LeafIcon className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />,
  },
  hazardous: {
    label: "Hazardous",
    badgeClass: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800",
    icon: <AlertTriangleIcon className="w-3.5 h-3.5 text-rose-600 dark:text-rose-400" />,
  },
  unknown: {
    label: "Uncategorized",
    badgeClass: "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
    icon: <BoxIcon className="w-3.5 h-3.5 text-slate-500" />,
  },
};

const STATUS_BADGES: Record<string, { label: string; badgeClass: string }> = {
  completed: {
    label: "Committed",
    badgeClass: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
  pending: {
    label: "Pending",
    badgeClass: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  },
  failed: {
    label: "Failed",
    badgeClass: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
  },
  reversed: {
    label: "Reversed",
    badgeClass: "bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300",
  },
  not_reported: {
    label: "Status not provided",
    badgeClass: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  },
};

export const RecentEvents: React.FC<RecentEventsProps> = ({ events = [], isLoading = false }) => {
  if (isLoading && events.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 animate-pulse h-80" aria-busy="true" />
    );
  }

  const formatTimestamp = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return iso;
    }
  };

  return (
    <section aria-labelledby="recent-events-title" className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ClockIcon className="w-4 h-4 text-slate-400" />
          <h2 id="recent-events-title" className="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Audit Log & Event Stream
          </h2>
        </div>
        <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
          {events.length} events
        </span>
      </div>

      <div className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-200 dark:border-slate-800 shadow-sm max-h-[460px] overflow-y-auto">
        {events.length === 0 ? (
          <div className="py-8 text-center text-slate-400">
            <CheckCircle2Icon className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
            <p className="text-xs font-medium text-slate-600 dark:text-slate-400">
              No audit events logged yet.
            </p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Items confirmed via the mobile scanner will record real-time telemetry here.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800" role="list">
            {events.map((evt) => {
              const categoryBadge = CATEGORY_EVENT_BADGES[evt.category] || {
                ...CATEGORY_EVENT_BADGES.unknown,
                label: evt.category,
              };
              const status = STATUS_BADGES[evt.processingStatus] || {
                label: evt.processingStatus,
                badgeClass: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
              };

              return (
                <li key={evt.id} className="py-3 first:pt-0 last:pb-0 flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5 min-w-0">
                    <div className="mt-0.5 shrink-0">
                      <span className={`inline-flex p-1.5 rounded-lg border ${categoryBadge.badgeClass}`}>
                        {categoryBadge.icon}
                      </span>
                    </div>

                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <p className="text-xs font-bold text-slate-900 dark:text-white truncate">
                          {evt.itemName}
                        </p>
                        <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${status.badgeClass}`}>
                          {status.label}
                        </span>
                      </div>

                      <p className="text-[11px] text-slate-500 dark:text-slate-400 flex items-center gap-2 mt-0.5">
                        <span>Destination: <span className="font-mono text-slate-700 dark:text-slate-300">{evt.destinationName || evt.destinationId || "Not recorded"}</span></span>
                        <span>•</span>
                        <span>Quantity: <span className="font-mono font-semibold">{evt.quantity} {evt.unit}</span></span>
                      </p>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <span className="text-[10px] font-mono text-slate-400 block">
                      {formatTimestamp(evt.timestamp)}
                    </span>
                    <span className="text-[9px] font-mono text-slate-400/80 uppercase">
                      {evt.eventType.replace(/_/g, " ")}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
};
