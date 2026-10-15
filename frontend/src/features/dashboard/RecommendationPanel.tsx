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
    label: "Operational Advisory",
    badgeClass: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
    borderClass: "border-blue-300 dark:border-blue-800",
    icon: <InfoIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />,
  },
  low: {
    label: "Informational",
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
          <SparklesIcon className="w-4 h-4 text-amber-500" />
          <h2 id="recommendations-title" className="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            AI Operations & Routing Insights
          </h2>
        </div>

        {/* Action Trigger for Backend Synthesis */}
        <div className="flex items-center gap-2">
          {onGenerateRecommendations ? (
            <button
              type="button"
              onClick={() => onGenerateRecommendations()}
              disabled={isGenerating || !canGenerate}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold shadow-xs disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-98"
              aria-label="Synthesize new recommendations via AI backend"
            >
              <SparklesIcon className={`w-3.5 h-3.5 ${isGenerating ? "animate-spin" : ""}`} />
              <span>{isGenerating ? "Synthesizing..." : "Generate Insights"}</span>
            </button>
          ) : (
            <span
              className="text-[11px] text-slate-400 italic"
              title="Awaiting backend integration hook"
            >
              Synthesis hook unmounted
            </span>
          )}
        </div>
      </div>

      <div className="space-y-3">
        {isLoading && recommendations.length === 0 ? (
          <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 animate-pulse h-48" aria-busy="true" />
        ) : recommendations.length === 0 ? (
          <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 text-center text-slate-400">
            <SparklesIcon className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto mb-2" />
            <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300">
              No Active Recommendations
            </h3>
            <p className="text-[11px] text-slate-400 max-w-sm mx-auto mt-1">
              Backend recommendations are generated when bin capacity thresholds are reached or material imbalances are detected.
            </p>
          </div>
        ) : (
          recommendations.map((rec) => {
            const config = SEVERITY_CONFIG[rec.severity] || SEVERITY_CONFIG.low;

            return (
              <div
                key={rec.id}
                className={`bg-white dark:bg-slate-900 rounded-2xl p-4 border ${config.borderClass} shadow-sm space-y-2`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {config.icon}
                    <h3 className="text-xs font-bold text-slate-900 dark:text-white">
                      {rec.title}
                    </h3>
                  </div>

                  <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${config.badgeClass}`}>
                    {config.label}
                  </span>
                </div>

                <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                  {rec.description}
                </p>

                {/* Supporting Metadata & Generation Provenance */}
                <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>Action: <strong className="text-slate-600 dark:text-slate-300">{rec.actionType || "Not provided"}</strong></span>
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
