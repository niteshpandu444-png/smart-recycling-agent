"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DashboardView } from "@/features/dashboard/DashboardView";
import {
  adaptEvents,
  adaptRecommendations,
  adaptSnapshot,
  eventsToMaterialFlows,
} from "@/features/dashboard/dashboard.adapters";
import {
  DashboardConnectionState,
  DashboardRestApiState,
} from "@/features/dashboard/dashboard.types";
import {
  ApiError,
  generateRecommendations,
  getEvents,
  getRecommendations,
  getTwinSnapshot,
  getWebSocketUrl,
} from "@/lib/api";
import {
  DigitalTwinSnapshot,
  EventHistoryResponse,
  RecommendationsResponse,
} from "@/types/api";

export default function DigitalTwinDashboardPage() {
  const [snapshot, setSnapshot] = useState<DigitalTwinSnapshot | null>(null);
  const [eventHistory, setEventHistory] = useState<EventHistoryResponse | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationsResponse>([]);
  const [connectionState, setConnectionState] = useState<DashboardConnectionState>("reconnecting");
  const [restApiState, setRestApiState] = useState<DashboardRestApiState>("checking");
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(async (showLoading = true) => {
    if (showLoading) setIsLoading(true);
    try {
      const [nextSnapshot, nextEvents, nextRecommendations] = await Promise.all([
        getTwinSnapshot(),
        getEvents(50),
        getRecommendations(),
      ]);
      setSnapshot(nextSnapshot);
      setEventHistory(nextEvents);
      setRecommendations(nextRecommendations);
      setErrorMessage(null);
      setRestApiState("available");
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError ? error.message : "Could not load Digital Twin data from the backend."
      );
      setRestApiState("unavailable");
    } finally {
      if (showLoading) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let retryDelay = 1000;

    void refresh();

    const connect = () => {
      if (!active) return;
      let socket: WebSocket;
      try {
        socket = new WebSocket(getWebSocketUrl());
      } catch {
        setConnectionState("reconnecting");
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 15000);
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        retryDelay = 1000;
        setConnectionState("connected");
      };
      socket.onmessage = (message) => {
        try {
          const envelope: unknown = JSON.parse(String(message.data));
          if (
            typeof envelope === "object" &&
            envelope !== null &&
            "type" in envelope &&
            typeof envelope.type === "string" &&
            envelope.type.length > 0
          ) {
            // The database remains authoritative; refresh its snapshot and history after notifications.
            void refresh(false);
          }
        } catch {
          setErrorMessage("The backend sent an unreadable live update. Snapshot refresh remains available.");
        }
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (!active) return;
        setConnectionState("reconnecting");
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 15000);
      };
    };

    connect();
    const pollingTimer = setInterval(() => void refresh(false), 30000);

    return () => {
      active = false;
      clearInterval(pollingTimer);
      if (retryTimer) clearTimeout(retryTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [refresh]);

  const handleGenerateRecommendations = useCallback(async () => {
    setIsGenerating(true);
    try {
      await generateRecommendations({ force_refresh: true });
      await refresh(false);
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError ? error.message : "Could not generate a recommendation from current backend state."
      );
    } finally {
      setIsGenerating(false);
    }
  }, [refresh]);

  const adapted = snapshot ? adaptSnapshot(snapshot) : null;
  const events = eventHistory && adapted ? adaptEvents(eventHistory, adapted.bins) : [];

  return (
    <DashboardView
      metrics={adapted?.metrics}
      bins={adapted?.bins}
      materialFlows={eventsToMaterialFlows(events)}
      events={events}
      recommendations={adaptRecommendations(recommendations)}
      connectionState={connectionState}
      restApiState={restApiState}
      lastSyncTimestamp={snapshot?.timestamp ?? null}
      isLoading={isLoading}
      errorMessage={errorMessage}
      onRefresh={() => refresh()}
      onGenerateRecommendations={handleGenerateRecommendations}
      isGeneratingRecommendations={isGenerating}
    />
  );
}
