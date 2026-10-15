/**
 * ==============================================================================
 * Smart Recycling Agent — Shared API Types & Contracts
 * ==============================================================================
 * This file serves as the canonical TypeScript interface definition across both
 * frontend components:
 * 1. Mobile Scanner UI (Item classification, review, confirmation)
 * 2. Digital Twin Dashboard UI (Inventory tracking, material flow, recommendations)
 *
 * All types mirror the contract specified in frontend/API_CONTRACT.md.
 * ==============================================================================
 */

/**
 * Standard classification categories recognized across the recycling system.
 */
export type RecyclingCategory =
  | "recyclable"
  | "reusable"
  | "biodegradable"
  | "hazardous";

/**
 * Model classification outcome status.
 * - 'success': Confidence threshold met; route determined.
 * - 'uncertain': Low confidence or ambiguous features; manual review required.
 * - 'failed': Image unclassifiable, obstructed, or unreadable.
 */
export type ClassificationStatus = "success" | "uncertain" | "failed";

/**
 * Standardized API error response format returned by backend endpoints.
 */
export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}

/**
 * GET /api/health
 */
export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  version: string;
  uptime_seconds?: number;
  timestamp: string;
}

/**
 * GET /api/model/status
 */
export interface ModelStatusResponse {
  model_identifier: string;
  is_loaded: boolean;
  device?: "cpu" | "cuda" | "mps" | string;
  inference_latency_ms?: number;
  supported_categories: RecyclingCategory[];
  version?: string;
}

/**
 * POST /api/scans
 * Request: multipart/form-data with field name 'file'
 */
export interface ScanClassificationResponse {
  scan_id: string;
  predicted_item: string;
  predicted_category: RecyclingCategory;
  /**
   * Model-specific confidence score (0.0 to 1.0).
   * Note: Treat as a model-relative score, not a guaranteed real-world probability.
   */
  match_score?: number | null;
  manual_review_recommended: boolean;
  suggested_route: string;
  explanation: string;
  model_identifier: string;
  classification_status: ClassificationStatus;
  created_at?: string;
}

/**
 * POST /api/scans/{id}/confirm
 * Request payload to verify or override the classification before recording in inventory.
 */
export interface ScanConfirmationRequest {
  confirmed_item: string;
  confirmed_category: RecyclingCategory;
  destination_id: string;
  /**
   * Client-generated UUID to prevent duplicate confirmations during network retries.
   */
  idempotency_key: string;
}

/**
 * POST /api/scans/{id}/confirm
 * Response confirming that the item has been committed to the Digital Twin inventory.
 */
export interface ScanConfirmationResponse {
  confirmation_id: string;
  scan_id: string;
  confirmed_item: string;
  confirmed_category: RecyclingCategory;
  destination_id: string;
  status: "recorded" | "duplicate" | "failed";
  recorded_at: string;
  updated_inventory_count?: number;
}

/**
 * Digital Twin bin state
 */
export interface DigitalTwinBin {
  id: string;
  name: string;
  category: RecyclingCategory;
  current_fill_kg: number;
  max_capacity_kg: number;
  fill_percentage: number;
  last_updated: string;
}

/**
 * GET /api/twin/snapshot
 * Used by the Digital Twin dashboard to render real-time material flows and inventory.
 */
export interface DigitalTwinSnapshot {
  snapshot_id: string;
  timestamp: string;
  bins: DigitalTwinBin[];
  total_items_processed: number;
  active_routes: number;
}

/**
 * GET /api/events
 */
export interface EventItem {
  event_id: string;
  event_type:
    | "scan_detected"
    | "scan_confirmed"
    | "route_updated"
    | "threshold_alert"
    | string;
  item_name: string;
  category: RecyclingCategory;
  destination_id: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface EventHistoryResponse {
  events: EventItem[];
  total_count: number;
}

/**
 * GET /api/recommendations
 */
export interface RecommendationItem {
  recommendation_id: string;
  title: string;
  description: string;
  severity: "low" | "medium" | "high" | "critical";
  action_type: "reroute" | "empty_bin" | "material_reuse" | "maintenance" | string;
  created_at: string;
}

export interface RecommendationsResponse {
  recommendations: RecommendationItem[];
  generated_at: string;
  based_on_snapshot_id?: string;
}

/**
 * POST /api/recommendations/generate
 */
export interface GenerateRecommendationsRequest {
  focus_category?: RecyclingCategory;
  include_historical_events?: boolean;
}

/**
 * WS /api/live
 * WebSocket message envelope for live streaming events between phone scanner, backend, and dashboard.
 */
export type WebSocketEventType =
  | "item_scanned"
  | "item_confirmed"
  | "bin_capacity_updated"
  | "recommendation_added"
  | "ping"
  | "pong";

export interface WebSocketLiveMessage<T = unknown> {
  type: WebSocketEventType;
  payload: T;
  timestamp: string;
}
