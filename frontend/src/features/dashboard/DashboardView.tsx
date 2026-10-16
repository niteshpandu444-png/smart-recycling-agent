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
import { AlertTriangleIcon, LeafIcon } from "./DashboardIcons";

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
    <div className="min-h-screen bg-slate-50 px-4 py-6 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-col gap-4 border-b border-slate-200 pb-5 md:flex-row md:items-end md:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-emerald-700 text-white">
              <LeafIcon className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-950">Recycling Operations</h1>
              <p className="mt-1 max-w-2xl text-sm text-slate-600">
                Recorded inventory, destination capacity, and recent material events.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 self-start md:self-auto">
            <Link href="/scanner" className="text-sm font-medium text-emerald-800 underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-800">
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

        {errorMessage && (
          <div role="alert" aria-live="assertive" className="flex items-start justify-between gap-4 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
            <div className="flex items-start gap-2">
              <AlertTriangleIcon className="mt-0.5 h-4 w-4 shrink-0 text-rose-700" />
              <div>
                <p className="font-medium">Data refresh issue</p>
                <p className="mt-0.5 text-rose-800">{errorMessage}</p>
              </div>
            </div>
            {onRefresh && (
              <button type="button" onClick={onRefresh} className="shrink-0 border border-rose-300 bg-white px-3 py-2 text-xs font-medium text-rose-900 hover:bg-rose-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-700">
                Retry
              </button>
            )}
          </div>
        )}

        <OverviewMetrics metrics={metrics} isLoading={isLoading} />
        <BatchActivityPanel metrics={metrics} isLoading={isLoading} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="space-y-6 lg:col-span-8">
            <VirtualBinGrid bins={bins} isLoading={isLoading} />
            <MaterialFlow flows={materialFlows} isLoading={isLoading} />
          </div>
          <aside className="space-y-6 lg:col-span-4" aria-label="Operations updates">
            <RecyclingAgentPanel canQuery={!isOffline} />
            <RecommendationPanel
              recommendations={recommendations}
              isLoading={isLoading}
              onGenerateRecommendations={onGenerateRecommendations}
              isGenerating={isGeneratingRecommendations}
              canGenerate={!isOffline}
            />
            <RecentEvents events={events} isLoading={isLoading} />
          </aside>
        </div>

        <footer className="flex flex-col gap-1 border-t border-slate-200 pt-4 text-xs text-slate-500 sm:flex-row sm:justify-between">
          <span>Smart Recycling Agent</span>
          <span>Data source: backend snapshot, event history, and live connection</span>
        </footer>
      </div>
    </div>
  );
};
