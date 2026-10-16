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

/**
 * GET /api/model/detector/status
 * Readiness and provenance of the mixed-waste object detector. This is a
 * separate artifact from the single-item classifier, with its own licence.
 */
export interface DetectorStatusResponse {
  initialized_successfully: boolean;
  inference_available: boolean;
  diagnostic_status: string;
  detector_identifier: string;
  detector_source: string;
  detector_license: string;
  detector_architecture: string;
  detector_class_names: string[];
  detection_score_threshold: number;
  nms_iou_threshold: number;
  same_object_iou_threshold: number;
  notes: string[];
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

/** POST /api/scans/preview, multipart field `file`; does not create a scan record. */
export interface ScanPreviewResponse {
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

/**
 * POST /api/scans/batch — one image containing several waste items.
 *
 * An empty `items` array is a real result meaning nothing was detected. It is
 * never a whole-image classification standing in for missing detections.
 */
export type BatchReviewStatus = "ready" | "needs_review";

/** A bounding box in both pixel and normalized image coordinates. */
export interface DetectionBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  normalized_x1: number;
  normalized_y1: number;
  normalized_x2: number;
  normalized_y2: number;
}

/** Independent whole-image classifier verdict for one item's crop. */
export interface CropCrossCheck {
  model_class: string;
  category: string;
  score: number;
  model_identifier: string;
}

export interface BatchScanItem {
  item_id: string;
  scan_id: string;
  detected_class: string;
  category: MaterialCategory;
  /** Detector score; not a calibrated probability. */
  score: number;
  margin: number | null;
  box: DetectionBox;
  review_status: BatchReviewStatus;
  review_reasons: string[];
  suggested_destination: string;
  attempts_holding_bin: boolean;
  guidance: string;
  cross_check: CropCrossCheck | null;
  metadata: Record<string, unknown>;
}

export interface BatchScanResponse {
  batch_id: string;
  image_width: number;
  image_height: number;
  detection_count: number;
  review_required_count: number;
  detector_identifier: string;
  detector_license: string;
  detector_diagnostic_status: string;
  items: BatchScanItem[];
  notes: string[];
}

/** POST /api/materials/confirm-batch */
export interface BatchConfirmItemRequest {
  scan_id: string;
  confirmed_category: MaterialCategory;
  item_id?: string;
  quantity?: number;
  unit?: string;
  destination_bin_id?: string;
  confirmation_source?: string;
  description?: string;
  verification_answers?: Record<string, unknown>;
  idempotency_key?: string;
}

export interface BatchConfirmRequest {
  batch_id?: string;
  items: BatchConfirmItemRequest[];
}

export interface BatchConfirmResultItem {
  item_id: string | null;
  scan_id: string;
  /** `confirmed` | `already_confirmed` | `failed` */
  status: string;
  material_id: string | null;
  confirmed_category: string | null;
  destination: string | null;
  processing_status: string | null;
  error: string | null;
}

/**
 * Batch confirmation is resolved per item, so `failed_count` above zero means a
 * partial outcome and not a successful batch.
 */
export interface BatchConfirmResponse {
  batch_id: string | null;
  confirmed_count: number;
  already_confirmed_count: number;
  failed_count: number;
  results: BatchConfirmResultItem[];
}

/** GET /api/twin/snapshot */
export interface DigitalTwinBin {
  id: string;
  name: string;
  accepted_category: string;
  current_inventory: number;
  capacity: number;
  inventory_unit: string;
  occupancy_percentage: number | null;
  status: string;
  contamination_risk: number;
}
/** One mixed-waste scene scan and how its items were resolved. */
export interface BatchActivity {
  batch_id: string;
  created_at: string;
  detection_count: number;
  review_required_count: number;
  /** Detected items that a user confirmed into inventory. */
  confirmed_count: number;
  pending_review_count: number;
}

export interface DigitalTwinSnapshot {
  timestamp: string;
  total_confirmed_items: number;
  category_inventory: Record<string, number>;
  bins: DigitalTwinBin[];
  processing_totals: Record<string, number>;
  pending_verification_count: number;
  /** Batch activity counts detected items, never confirmed inventory. */
  batch_scan_count?: number;
  detected_item_totals?: Record<string, number>;
  needs_review_scan_count?: number;
  confirmed_from_batch_count?: number;
  recent_batch_activity?: BatchActivity[];
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
  payload: Record<string, unknown> | null;
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

/** Recycling Intelligence Agent v1 types */
export interface ToolEvidence {
  tool_name: string;
  arguments: Record<string, unknown>;
  summary: string;
  result_preview?: Record<string, unknown> | null;
}

export interface AgentMessageRequest {
  message: string;
  conversation_id?: string | null;
  context?: Record<string, unknown> | null;
}

export interface AgentMessageResponse {
  agent_mode: "live_llm" | "deterministic_fallback" | "disabled" | string;
  answer: string;
  is_fallback: boolean;
  tool_calls: ToolEvidence[];
  recommended_action?: string | null;
  supporting_facts?: Record<string, unknown>;
  model_identifier?: string | null;
  timestamp: string;
}

export interface AgentStatusResponse {
  enabled: boolean;
  agent_mode: string;
  provider_configured: boolean;
  model: string | null;
  base_url: string | null;
  available_tools: string[];
}
