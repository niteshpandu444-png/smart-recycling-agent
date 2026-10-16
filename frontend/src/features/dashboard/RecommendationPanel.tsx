import React from "react";
import { DashboardRecommendation } from "./dashboard.types";
import { SparklesIcon, ShieldAlertIcon, AlertTriangleIcon, CheckCircle2Icon, InfoIcon } from "./DashboardIcons";

interface RecommendationPanelProps {
  recommendations?: DashboardRecommendation[];
  isLoading?: boolean;
  onGenerateRecommendations?: () => Promise<void> | void;
  isGenerating?: boolean;
  canGenerate?: boolean;
}

const SEVERITY_CONFIG: Record<
  string,
  { label: string; badgeClass: string; borderClass: string; icon: React.ReactNode }
> = {
  critical: {
    label: "Critical Action",
    badgeClass: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
    borderClass: "border-rose-300 dark:border-rose-800",
    icon: <ShieldAlertIcon className="w-4 h-4 text-rose-600 dark:text-rose-400" />,
  },
  high: {
    label: "High Priority",
    badgeClass: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    borderClass: "border-amber-300 dark:border-amber-800",
    icon: <AlertTriangleIcon className="w-4 h-4 text-amber-600 dark:text-amber-400" />,
  },
  medium: {
    label: "Medium",
    badgeClass: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    borderClass: "border-slate-200 dark:border-slate-800",
    icon: <InfoIcon className="w-4 h-4 text-slate-600 dark:text-slate-400" />,
  },
  low: {
    label: "Low",
    badgeClass: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300",
    borderClass: "border-slate-200 dark:border-slate-800",
    icon: <CheckCircle2Icon className="w-4 h-4 text-slate-500" />,
  },
  unknown: {
    label: "Priority not provided",
    badgeClass: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    borderClass: "border-slate-200 dark:border-slate-800",
    icon: <InfoIcon className="w-4 h-4 text-slate-500" />,
  },
};

export const RecommendationPanel: React.FC<RecommendationPanelProps> = ({
  recommendations = [],
  isLoading = false,
  onGenerateRecommendations,
  isGenerating = false,
  canGenerate = true,
}) => {
  return (
    <section aria-labelledby="recommendations-title" className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
      <div className="flex items-center gap-2">
          <h2 id="recommendations-title" className="text-sm font-semibold text-slate-900">
            Backend recommendations
          </h2>
        </div>

        {/* Action Trigger for Backend Synthesis */}
        <div className="flex items-center gap-2">
          {onGenerateRecommendations ? (
            <button
              type="button"
              onClick={() => onGenerateRecommendations()}
              disabled={isGenerating || !canGenerate}
              className="inline-flex min-h-9 items-center gap-1.5 border border-emerald-800 bg-emerald-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-900 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
              aria-label="Request a recommendation from the backend"
              title={canGenerate ? "Request a recommendation from the backend" : "Available when the backend is connected"}
            >
              <SparklesIcon className={`w-3.5 h-3.5 ${isGenerating ? "animate-spin" : ""}`} />
              <span>{isGenerating ? "Requesting…" : "Generate recommendation"}</span>
            </button>
          ) : (
            null
          )}
        </div>
      </div>

      <div className="space-y-3">
        {isLoading && recommendations.length === 0 ? (
          <div className="h-32 border border-slate-200 bg-white" aria-busy="true" aria-label="Loading recommendations" />
        ) : recommendations.length === 0 ? (
          <div className="border border-slate-200 bg-white p-4 text-sm text-slate-600">
            <h3 className="font-medium text-slate-800">
              No recommendations returned
            </h3>
            <p className="text-[11px] text-slate-400 max-w-sm mx-auto mt-1">
              The backend has not returned any recommendation records.
            </p>
          </div>
        ) : (
          recommendations.map((rec) => {
            const config = SEVERITY_CONFIG[rec.severity ?? "unknown"] || SEVERITY_CONFIG.unknown;

            return (
              <div
                key={rec.id}
                className={`space-y-2 border bg-white p-4 ${config.borderClass}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {config.icon}
                    <h3 className="text-xs font-bold text-slate-900 dark:text-white">
                      {rec.title}
                    </h3>
                  </div>

                  <span className={`border px-2 py-1 text-[10px] font-medium ${config.badgeClass}`}>
                    {config.label}
                  </span>
                </div>

                <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                  {rec.description}
                </p>

                {/* Supporting Metadata & Generation Provenance */}
                <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>Action: <strong className="text-slate-600 dark:text-slate-300">{rec.actionType || "Unavailable"}</strong></span>
                  {rec.status && (
                    <span>Status: <strong className="text-slate-600 dark:text-slate-300">{rec.status}</strong></span>
                  )}
                  {rec.generationMethod && (
                    <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
                      Method: {rec.generationMethod}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
};
