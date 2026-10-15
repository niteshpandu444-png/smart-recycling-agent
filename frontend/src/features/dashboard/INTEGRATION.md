# Digital Twin Dashboard — Integration Guide & Contract Mapping

**Feature Directory:** `frontend/src/features/dashboard/`
**Target Integration Branch:** `origin/feat/frontend-scanner-foundation`
**Backend Persistence Branch:** `origin/feat/backend-data-twin`
**Current Phase:** Phase 1 (Isolated Presentation Components)

---

## 1. Overview & Architectural Isolation

During Phase 1, all dashboard presentation components were built in strict isolation inside `frontend/src/features/dashboard/`. They have **zero dependencies on unmerged branches**, no speculative imports, and no duplicated API clients or duplicate types.

When the frontend foundation (`origin/feat/frontend-scanner-foundation`) is merged into this branch or into `main`, the components in this directory will be wired to the centralized API client (`@/lib/api`) and shared types (`@/types/api`).

---

## 2. Shared API Functions & Field-by-Field Mapping

The dashboard is designed to connect to the 4 shared asynchronous functions exported from `frontend/src/lib/api.ts`:

### 2.1 Digital Twin Snapshot: `getTwinSnapshot()`
* **Endpoint:** `GET /api/twin/snapshot`
* **Shared Type:** `DigitalTwinSnapshot` from `@/types/api.ts`
* **Target Presentation Models:** `DashboardOverviewMetrics` and `DashboardBin[]`

#### Schema Verification & Transformation:
| Shared API Field (`DigitalTwinSnapshot`) | Presentation Field (`DashboardOverviewMetrics` / `DashboardBin`) | Transformation Rule |
| :--- | :--- | :--- |
| `snapshot_id: string` | (internal reference) | Stored in sync state metadata |
| `timestamp: string` | `snapshotTimestamp: string` | Direct assignment |
| `total_items_processed: number` | `totalConfirmedItems: number` | Direct assignment (tagged as `OBSERVED`) |
| `active_routes: number` | `activeRoutesCount: number` | Direct assignment (tagged as `OBSERVED`) |
| `bins: DigitalTwinBin[]` | `bins: DashboardBin[]` | Mapped via bin adapter (see below) |

#### Bin Record Mapping:
| Shared API Field (`DigitalTwinBin`) | Presentation Field (`DashboardBin`) | Transformation Rule |
| :--- | :--- | :--- |
| `id: string` | `id: string` | Direct assignment |
| `name: string` | `name: string` | Direct assignment |
| `category: RecyclingCategory` | `category: DashboardMaterialCategory` | Strict union matching: `'recyclable'`, `'reusable'`, `'biodegradable'`, `'hazardous'` |
| `current_fill_kg: number` | `currentInventory: number` | Direct assignment |
| `max_capacity_kg: number` | `capacity: number` | Direct assignment; if `<= 0`, marked unconfigured |
| `fill_percentage: number` | `occupancyPercentage: number` | Direct assignment; verified for overflow (> 100%) |
| `last_updated: string` | `lastUpdated: string` | Direct assignment |
| (inferred) | `inventoryUnit: string` | Default to `'kg'` based on field suffix `_kg` |
| (inferred) | `status: BinOperationalStatus` | Derived: `fill_percentage >= 90 ? 'critical' : fill_percentage >= 75 ? 'warning' : 'normal'` |

---

### 2.2 Event Stream & Audit History: `getEvents(limit = 50)`
* **Endpoint:** `GET /api/events?limit=50`
* **Shared Type:** `EventHistoryResponse` containing `EventItem[]` from `@/types/api.ts`
* **Target Presentation Model:** `DashboardEvent[]`

#### Event Record Mapping:
| Shared API Field (`EventItem`) | Presentation Field (`DashboardEvent`) | Transformation Rule |
| :--- | :--- | :--- |
| `event_id: string` | `id: string` | Direct assignment |
| `event_type: string` | `eventType: string` | Standardizes `'scan_confirmed'`, `'route_updated'`, etc. |
| `item_name: string` | `itemName: string` | Direct assignment |
| `category: RecyclingCategory` | `category: DashboardMaterialCategory` | Mapped to category union |
| `destination_id: string` | `destinationId: string` | Direct assignment |
| `timestamp: string` | `timestamp: string` | Direct assignment |
| `metadata: Record<string, unknown>` | `metadata` | Passed for detailed inspection |
| (inferred) | `quantity: number` | Defaults to `1` (or extracts from `metadata.quantity`) |
| (inferred) | `unit: string` | Defaults to `'items'` |
| (inferred) | `processingStatus: string` | Defaults to `'completed'` for confirmed events |

---

### 2.3 AI Recommendations: `getRecommendations()`
* **Endpoint:** `GET /api/recommendations`
* **Shared Type:** `RecommendationsResponse` containing `RecommendationItem[]` from `@/types/api.ts`
* **Target Presentation Model:** `DashboardRecommendation[]`

#### Recommendation Record Mapping:
| Shared API Field (`RecommendationItem`) | Presentation Field (`DashboardRecommendation`) | Transformation Rule |
| :--- | :--- | :--- |
| `recommendation_id: string` | `id: string` | Direct assignment |
| `title: string` | `title: string` | Direct assignment |
| `description: string` | `description: string` | Direct assignment |
| `severity: "low"\|"medium"\|"high"\|"critical"` | `severity` | Direct union match |
| `action_type: string` | `actionType` | Direct assignment (`'empty_bin'`, `'reroute'`, etc.) |
| `created_at: string` | `createdAt: string` | Direct assignment |

---

### 2.4 Generative AI Trigger: `generateRecommendations()`
* **Endpoint:** `POST /api/recommendations/generate`
* **Shared Client Call:** `generateRecommendations()` from `@/lib/api.ts`
* **UI Hook:** Directly wired to `onGenerateRecommendations` prop in `DashboardView.tsx`.
* **Guardrail:** The button remains honestly disabled if the backend is offline or unreachable.

---

## 3. Real-Time Streaming (`WS /api/live`)

When WebSocket support is wired:
1. Establish connection to `ws://<HOST>:8000/api/live` using `getWebSocketUrl()` from `@/lib/api`.
2. Listen for envelopes matching `WebSocketLiveMessage<T>`:
   - On `item_confirmed`: Increment total items, append to `RecentEvents`, and trigger background snapshot re-fetch.
   - On `bin_capacity_updated`: Update the corresponding bin in `VirtualBinGrid`.
   - On `recommendation_added`: Prepend new recommendation into `RecommendationPanel`.
3. If the WebSocket disconnects, `ConnectionStatus.tsx` automatically transitions to `"reconnecting"` or `"offline"`, falling back to periodic REST polling.

---

## 4. Example Integration Adapter (Phase 2 Preview)

When the branch is merged with the foundation, the container component in `src/app/dashboard/page.tsx` will look like this:

```typescript
// Example: src/app/dashboard/page.tsx (to be created in Phase 2)
"use client";

import React, { useEffect, useState, useCallback } from "react";
import { getTwinSnapshot, getEvents, getRecommendations, generateRecommendations, getHealth } from "@/lib/api";
import { DashboardView } from "@/features/dashboard/DashboardView";
import { adaptTwinSnapshot, adaptEvents, adaptRecommendations } from "@/features/dashboard/adapters";
import { DashboardConnectionState } from "@/features/dashboard/dashboard.types";

export default function DashboardPage() {
  const [connectionState, setConnectionState] = useState<DashboardConnectionState>("reconnecting");
  const [snapshot, setSnapshot] = useState(null);
  const [events, setEvents] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [snapData, evtData, recData] = await Promise.all([
        getTwinSnapshot(),
        getEvents(50),
        getRecommendations(),
      ]);
      setSnapshot(snapData);
      setEvents(evtData.events);
      setRecommendations(recData.recommendations);
      setConnectionState("connected");
    } catch (err) {
      setConnectionState("offline");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const updated = await generateRecommendations();
      setRecommendations(updated.recommendations);
    } finally {
      setIsGenerating(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const { metrics, bins, materialFlows } = adaptTwinSnapshot(snapshot, events);

  return (
    <DashboardView
      metrics={metrics}
      bins={bins}
      materialFlows={materialFlows}
      events={adaptEvents(events)}
      recommendations={adaptRecommendations(recommendations)}
      connectionState={connectionState}
      lastSyncTimestamp={snapshot?.timestamp}
      isLoading={isLoading}
      onRefresh={fetchData}
      onGenerateRecommendations={handleGenerate}
      isGeneratingRecommendations={isGenerating}
    />
  );
}
```

---

## 5. Summary of Isolated Deliverables

All components built in Phase 1 adhere strictly to the following principles:
- **Zero file pollution:** All files are contained in `frontend/src/features/dashboard/`.
- **Zero mock data invention:** Presentation components cleanly handle real empty states and true backend values without invented fixtures.
- **Strict calculation honesty:** Capacity percentages and flow distributions are only calculated when valid figures exist.
- **Ready for seamless integration:** Perfectly aligned with `frontend/API_CONTRACT.md` and `origin/feat/frontend-scanner-foundation`.
