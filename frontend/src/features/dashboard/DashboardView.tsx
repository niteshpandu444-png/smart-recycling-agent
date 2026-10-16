import React from "react";
import Link from "next/link";
import { DashboardViewProps } from "./dashboard.types";
import { ConnectionStatus } from "./ConnectionStatus";
import { OverviewMetrics } from "./OverviewMetrics";
import { BatchActivityPanel } from "./BatchActivityPanel";
import { VirtualBinGrid } from "./VirtualBinGrid";
import { MaterialFlow } from "./MaterialFlow";
import { RecentEvents } from "./RecentEvents";
import { RecommendationPanel } from "./RecommendationPanel";
import { RecyclingAgentPanel } from "./RecyclingAgentPanel";
import { LeafIcon, AlertTriangleIcon } from "./DashboardIcons";

export const DashboardView: React.FC<DashboardViewProps> = ({
  metrics,
  bins = [],
  materialFlows = [],
  events = [],
  recommendations = [],
  connectionState,
  restApiState,
  lastSyncTimestamp,
  isLoading = false,
  errorMessage,
  onRefresh,
  onGenerateRecommendations,
  isGeneratingRecommendations = false,
}) => {
  const isOffline = restApiState === "unavailable";

  return (
    <div className="w-full min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 px-4 sm:px-6 lg:px-8 py-6 safe-top safe-bottom">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Top Header Bar */}
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-sm shrink-0">
              <LeafIcon className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-extrabold tracking-tight text-slate-900 dark:text-white leading-tight">
                  Digital Twin Operations Dashboard
                </h1>
                <span className="text-[10px] font-bold font-mono uppercase px-2 py-0.5 rounded bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300 border border-brand-200 dark:border-brand-800">
                  PS 06
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Persisted material flow, bin telemetry, and deterministic guidance
              </p>
            </div>
          </div>

          {/* Connection Status & Sync Controls */}
          <div className="flex items-center gap-3 self-start md:self-auto">
            <Link href="/" className="text-xs font-semibold text-brand-700 hover:text-brand-600 dark:text-brand-300">
              Open scanner
            </Link>
            <ConnectionStatus
              connectionState={connectionState}
              restApiState={restApiState}
              lastSyncTimestamp={lastSyncTimestamp}
              isLoading={isLoading}
              onRefresh={onRefresh}
            />
          </div>
        </header>

        {/* Global Error Banner */}
        {errorMessage && (
          <div
            role="alert"
            aria-live="assertive"
            className="p-4 rounded-2xl bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-900 text-rose-800 dark:text-rose-200 flex items-start justify-between gap-3 text-xs"
          >
            <div className="flex items-start gap-2.5">
              <AlertTriangleIcon className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-bold">Sync Issue Detected</p>
                <p className="mt-0.5 text-rose-700 dark:text-rose-300">{errorMessage}</p>
              </div>
            </div>
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-semibold shrink-0 transition-colors"
              >
                Retry Query
              </button>
            )}
          </div>
        )}

        {/* Section 1: Overview Telemetry & Material Distribution Bar */}
        <OverviewMetrics metrics={metrics} isLoading={isLoading} />

        {/* Section 2: Mixed-Waste Batch Activity (detected vs confirmed) */}
        <BatchActivityPanel metrics={metrics} isLoading={isLoading} />

        {/* Section 3: Main Operational Workspace (Laptop 2-Column Split) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column (8 cols): Virtual Bin Grid + Material Flow */}
          <div className="lg:col-span-8 space-y-6">
            <VirtualBinGrid bins={bins} isLoading={isLoading} />
            <MaterialFlow flows={materialFlows} isLoading={isLoading} />
          </div>

          {/* Right Rail (4 cols): Recycling Intelligence Agent + Recommendations + Recent Audit Log */}
          <div className="lg:col-span-4 space-y-6">
            <RecyclingAgentPanel canQuery={!isOffline} />
            <RecommendationPanel
              recommendations={recommendations}
              isLoading={isLoading}
              onGenerateRecommendations={onGenerateRecommendations}
              isGenerating={isGeneratingRecommendations}
              canGenerate={!isOffline}
            />
            <RecentEvents events={events} isLoading={isLoading} />
          </div>
        </div>

        {/* Footer System Telemetry Notes */}
        <footer className="pt-6 border-t border-slate-200 dark:border-slate-800 text-[11px] text-slate-400 dark:text-slate-500 flex flex-col sm:flex-row justify-between items-center gap-2 text-center sm:text-left">
          <p>
            Smart Recycling Agent • Code Clash 2.0 • Digital Twin Material Flow Protocol
          </p>
          <div className="flex items-center gap-2 font-mono">
            <span>State source: backend persistence</span>
          </div>
        </footer>
      </div>
    </div>
  );
};
