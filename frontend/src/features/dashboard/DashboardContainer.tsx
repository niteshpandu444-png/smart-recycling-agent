"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  generateRecommendations,
  getApiBaseUrl,
  getEvents,
  getRecommendations,
  getTwinSnapshot,
} from "@/lib/api";
import type {
  DigitalTwinSnapshot,
  EventItem,
  RecommendationItem,
  WebSocketLiveMessage,
} from "@/types/api";
import { DashboardView } from "./DashboardView";
import {
  adaptEvents,
  adaptRecommendations,
  adaptSnapshot,
} from "./dashboard.adapters";
import type { DashboardConnectionState } from "./dashboard.types";

function websocketUrl(): string {
  const url = new URL(getApiBaseUrl());
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `${url.pathname.replace(/\/+$/, "")}/ws`;
  url.search = "";
  url.hash = "";
  return url.toString();
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Dashboard data could not be refreshed.";
}

function isDigitalTwinSnapshot(value: unknown): value is DigitalTwinSnapshot {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<DigitalTwinSnapshot>;
  return (
    typeof candidate.timestamp === "string" &&
    typeof candidate.total_confirmed_items === "number" &&
    typeof candidate.category_inventory === "object" &&
    candidate.category_inventory !== null &&
    !Array.isArray(candidate.category_inventory) &&
    Array.isArray(candidate.bins) &&
    typeof candidate.pending_verification_count === "number"
  );
}

export function DashboardContainer() {
  const [snapshot, setSnapshot] = useState<DigitalTwinSnapshot | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [connectionState, setConnectionState] = useState<DashboardConnectionState>("reconnecting");
  const [lastSyncTimestamp, setLastSyncTimestamp] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const socketOpen = useRef(false);
  const hasSnapshot = useRef(false);
  const requestId = useRef(0);

  const refreshData = useCallback(async (showLoading = false) => {
    const id = ++requestId.current;
    if (showLoading) setIsLoading(true);

    const results = await Promise.allSettled([
      getTwinSnapshot(),
      getEvents(50),
      getRecommendations(),
    ] as const);
    if (id !== requestId.current) return;

    const failures: string[] = [];
    const [snapshotResult, eventsResult, recommendationsResult] = results;

    if (snapshotResult.status === "fulfilled") {
      setSnapshot(snapshotResult.value);
      hasSnapshot.current = true;
      setLastSyncTimestamp(snapshotResult.value.timestamp);
    } else {
      failures.push(`Snapshot: ${errorMessage(snapshotResult.reason)}`);
    }
    if (eventsResult.status === "fulfilled") {
      setEvents(eventsResult.value.items);
    } else {
      failures.push(`Event history: ${errorMessage(eventsResult.reason)}`);
    }
    if (recommendationsResult.status === "fulfilled") {
      setRecommendations(recommendationsResult.value);
    } else {
      failures.push(`Recommendations: ${errorMessage(recommendationsResult.reason)}`);
    }

    if (failures.length > 0) {
      setError(failures.join(" "));
      setConnectionState(hasSnapshot.current || snapshotResult.status === "fulfilled" ? "stale" : "offline");
    } else {
      setError(null);
      setConnectionState(socketOpen.current ? "connected" : "reconnecting");
    }
    setIsLoading(false);
  }, []);

  useEffect(() => {
    void refreshData(true);
  }, [refreshData, refreshKey]);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let retryDelay = 1000;

    const connect = () => {
      if (disposed) return;
      setConnectionState((current) => current === "offline" ? "offline" : "reconnecting");
      socket = new WebSocket(websocketUrl());

      socket.onopen = () => {
        if (disposed) return;
        socketOpen.current = true;
        retryDelay = 1000;
        setConnectionState("connected");
        void refreshData();
      };

      socket.onmessage = (event) => {
        if (disposed) return;
        let message: WebSocketLiveMessage<unknown>;
        try {
          message = JSON.parse(String(event.data)) as WebSocketLiveMessage<unknown>;
        } catch {
          setError("The live connection sent an unreadable message.");
          return;
        }
        if (typeof message !== "object" || message === null || typeof message.type !== "string") {
          setError("The live connection sent an invalid message envelope.");
          return;
        }

        if (message.type === "snapshot" && isDigitalTwinSnapshot(message.data)) {
          setSnapshot(message.data);
          hasSnapshot.current = true;
          setLastSyncTimestamp(message.data.timestamp);
        }

        // Backend event envelopes are emitted only after commit; REST snapshots and
        // histories remain authoritative for the displayed aggregate state.
        if (message.type !== "snapshot" || message.data) void refreshData();
      };

      socket.onerror = () => {
        socket?.close();
      };

      socket.onclose = () => {
        if (disposed) return;
        socketOpen.current = false;
        setConnectionState((current) => current === "stale" || current === "offline" ? current : "reconnecting");
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000);
      };
    };

    connect();
    return () => {
      disposed = true;
      socketOpen.current = false;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, [refreshData]);

  const handleGenerateRecommendations = useCallback(async () => {
    setIsGenerating(true);
    setError(null);
    try {
      const generated = await generateRecommendations();
      setRecommendations((current) => [
        generated,
        ...current.filter((item) => item.id !== generated.id),
      ]);
    } catch (generationError) {
      setError(`Recommendation generation failed: ${errorMessage(generationError)}`);
    } finally {
      setIsGenerating(false);
    }
  }, []);

  const viewModel = snapshot ? adaptSnapshot(snapshot) : null;

  return (
    <DashboardView
      metrics={viewModel?.metrics}
      bins={viewModel?.bins}
      materialFlows={viewModel?.materialFlows}
      events={adaptEvents(events, snapshot)}
      recommendations={adaptRecommendations(recommendations)}
      connectionState={connectionState}
      lastSyncTimestamp={lastSyncTimestamp}
      isLoading={isLoading}
      errorMessage={error}
      onRefresh={() => setRefreshKey((key) => key + 1)}
      onGenerateRecommendations={handleGenerateRecommendations}
      isGeneratingRecommendations={isGenerating}
    />
  );
}
