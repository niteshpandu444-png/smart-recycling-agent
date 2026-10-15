/** Shared frontend types matching the FastAPI integration contract. */

export type ClassificationCategory = "recyclable" | "reusable" | "biodegradable" | "hazardous";
export type MaterialCategory =
  | "plastic"
  | "paper"
  | "metal"
  | "glass"
  | "organic"
  | "biodegradable"
  | "compostable"
  | "holding"
  | "hazardous"
  | "reusable";
export type ClassificationStatus = "success" | "uncertain";

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}
export interface ApiErrorResponse { error: ApiErrorDetail }

/** GET /api/health */
export interface HealthResponse { status: "ok" }

/** GET /api/model/status */
export interface ModelStatusResponse {
  initialized_successfully: boolean;
  model_identifier: string;
  inference_available: boolean;
  diagnostic_status: string;
}

/** POST /api/scans, multipart field `file`. */
export interface ScanClassificationResponse {
  scan_id: string;
  predicted_item: string | null;
  predicted_category: ClassificationCategory | null;
  /** Model-specific score; it is not a calibrated probability. */
  match_score: number | null;
  manual_review_recommended: boolean;
  suggested_route: string;
  explanation: string;
  model_identifier: string;
  classification_status: ClassificationStatus;
}

/** POST /api/materials/confirm. `destination_bin_id` is optional; backend routing applies when omitted. */
export interface ScanConfirmationRequest {
  scan_id: string;
  confirmed_category: MaterialCategory;
  quantity?: number;
  unit?: string;
  destination_bin_id?: string;
  confirmation_source?: "model_accepted" | "user_corrected" | "manual_review" | string;
  description?: string;
  verification_answers?: Record<string, unknown>;
  idempotency_key?: string;
}

/** POST /api/materials/confirm (HTTP 201). */
export interface ScanConfirmationResponse {
  id: string;
  scan_id: string;
  description: string | null;
  category: MaterialCategory;
  confirmed_category: MaterialCategory;
  predicted_category: string | null;
  quantity: number;
  unit: string;
  destination: string;
  processing_status: string;
  confirmation_source: string;
  confidence_at_confirmation: number | null;
  verification_answers: Record<string, unknown> | null;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

/** GET /api/twin/snapshot */
export interface DigitalTwinBin {
  id: string;
  name: string;
  accepted_category: string;
  current_inventory: number;
  capacity: number;
  inventory_unit: string;
  occupancy_percentage: number;
  status: string;
  contamination_risk: number;
}
export interface DigitalTwinSnapshot {
  timestamp: string;
  total_confirmed_items: number;
  category_inventory: Record<string, number>;
  bins: DigitalTwinBin[];
  processing_totals: Record<string, number>;
  pending_verification_count: number;
}

/** GET /api/events */
export interface EventItem {
  id: string;
  event_type: string;
  material_id: string | null;
  scan_id: string | null;
  source_bin_id: string | null;
  destination_bin_id: string | null;
  quantity: number;
  unit: string;
  affected_category: string | null;
  payload: Record<string, unknown>;
  idempotency_key: string | null;
  is_demo: boolean;
  timestamp: string;
}
export interface EventHistoryResponse {
  items: EventItem[];
  next_cursor: string | null;
  total_count: number;
}

/** GET /api/recommendations returns an array; generate returns one item. */
export interface RecommendationItem {
  id: string;
  title: string;
  recommendation_text: string;
  generation_method: string;
  supporting_data: Record<string, unknown>;
  status: string;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}
export type RecommendationsResponse = RecommendationItem[];
export interface GenerateRecommendationsRequest { force_refresh?: boolean }

/** WebSocket endpoint /ws sends a snapshot envelope and material event envelopes. */
export interface WebSocketLiveMessage<T = unknown> {
  type: "snapshot" | "material_confirmed" | "material_routed" | string;
  data: T;
}
