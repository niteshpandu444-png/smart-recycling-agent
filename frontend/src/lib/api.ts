/**
 * ==============================================================================
 * Smart Recycling Agent — Centralized API Client
 * ==============================================================================
 * Responsible for all HTTP communication with the Python FastAPI backend.
 * Provides strictly-typed methods, timeout control, network error normalization,
 * and user-friendly error messages.
 *
 * NOTE: The backend remains the single source of truth for predictions,
 * digital twin inventories, and AI recommendations.
 * ==============================================================================
 */

import {
  HealthResponse,
  ModelStatusResponse,
  DetectorStatusResponse,
  ScanClassificationResponse,
  ScanPreviewResponse,
  ScanConfirmationRequest,
  ScanConfirmationResponse,
  BatchScanResponse,
  BatchConfirmRequest,
  BatchConfirmResponse,
  DigitalTwinSnapshot,
  EventHistoryResponse,
  RecommendationsResponse,
  RecommendationItem,
  GenerateRecommendationsRequest,
  ApiErrorResponse,
  AgentMessageRequest,
  AgentMessageResponse,
  AgentStatusResponse,
} from "@/types/api";

/**
 * Standard Application Error encapsulating HTTP status, backend error codes,
 * and user-friendly explanations.
 */
export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly details?: unknown;

  constructor(message: string, status = 500, code = "UNKNOWN_ERROR", details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

/**
 * Resolves the API base URL from client environment variables or fallback.
 */
export function getApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const configuredUrl = envUrl?.trim();
  const fallbackUrl = process.env.NODE_ENV === "development"
    ? "http://localhost:8000"
    : "https://smart-recycling-agent-production.up.railway.app";
  const baseUrl = (configuredUrl || fallbackUrl).replace(/\/+$/, "");
  // API methods below own their `/api/...` paths. Accept a configured root
  // with or without a trailing `/api`, but never generate `/api/api/...`.
  return baseUrl.replace(/\/api$/i, "");
}

/** Resolves the backend's documented WebSocket endpoint (`/ws`). */
export function getWebSocketUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_WS_URL;
  const url = new URL(configuredUrl?.trim() || getApiBaseUrl());
  url.protocol = url.protocol === "https:" || url.protocol === "wss:" ? "wss:" : "ws:";
  url.pathname = "/ws";
  url.search = "";
  url.hash = "";
  return url.toString();
}

/**
 * Generates an RFC4122 v4 UUID using crypto.randomUUID or crypto.getRandomValues.
 */
export function generateIdempotencyKey(): string {
  if (typeof crypto !== "undefined") {
    if (typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    if (typeof crypto.getRandomValues === "function") {
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      // RFC4122 version 4 and variant 10xx bits
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
  }
  return "idemp-" + Date.now() + "-" + Math.random().toString(36).substring(2, 11);
}

/**
 * Configuration options for fetch execution.
 */
interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

/**
 * Internal fetch wrapper with AbortController timeout and error handling.
 */
async function fetchWithTimeout(url: string, options: RequestOptions = {}): Promise<Response> {
  const { timeoutMs = 15000, ...fetchOptions } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
    });
    return response;
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        `Request timed out after ${Math.round(timeoutMs / 1000)}s. The backend may be busy or offline.`,
        408,
        "TIMEOUT"
      );
    }
    if (err instanceof TypeError && err.message.includes("fetch")) {
      throw new ApiError(
        `Unable to reach backend at ${getApiBaseUrl()}. Please verify your network connection and backend service status.`,
        0,
        "NETWORK_DISCONNECTED"
      );
    }
    throw new ApiError(
      err instanceof Error ? err.message : "Failed to execute network request",
      0,
      "FETCH_FAILED"
    );
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Parses and handles JSON response with error schema inspection.
 */
async function handleResponse<T>(response: Response): Promise<T> {
  let responseData: unknown = null;
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    try {
      responseData = await response.json();
    } catch {
      throw new ApiError(
        "Invalid JSON response received from backend.",
        response.status,
        "INVALID_JSON"
      );
    }
  } else {
    // Non-JSON response (e.g. 502/504 Bad Gateway from reverse proxy)
    const text = await response.text().catch(() => "");
    if (!response.ok) {
      throw new ApiError(
        text || `Server returned unexpected status ${response.status} (${response.statusText}).`,
        response.status,
        "UNEXPECTED_RESPONSE"
      );
    }
  }

  if (!response.ok) {
    // Check if response matches standardized ApiErrorResponse schema
    const errorBody = responseData as ApiErrorResponse | null;
    if (errorBody && errorBody.error && typeof errorBody.error.message === "string") {
      throw new ApiError(
        errorBody.error.message,
        response.status,
        errorBody.error.code || "API_ERROR",
        errorBody.error.details
      );
    }

    // Generic FastAPI detail structure fallback: { detail: "..." }
    const fastapiDetail = (responseData as { detail?: string | unknown[] })?.detail;
    if (typeof fastapiDetail === "string") {
      throw new ApiError(fastapiDetail, response.status, "BAD_REQUEST");
    } else if (Array.isArray(fastapiDetail)) {
      // Pydantic validation errors
      const messages = fastapiDetail
        .map((d: unknown) => {
          if (typeof d === "object" && d !== null && "msg" in d) {
            const msgVal = (d as { msg: unknown }).msg;
            if (typeof msgVal === "string") {
              return msgVal;
            }
          }
          return JSON.stringify(d);
        })
        .join("; ");
      throw new ApiError(`Validation error: ${messages}`, response.status, "VALIDATION_ERROR", fastapiDetail);
    }

    throw new ApiError(
      `Request failed with status ${response.status} (${response.statusText}).`,
      response.status,
      "HTTP_ERROR",
      responseData
    );
  }

  return responseData as T;
}

// ==============================================================================
// Exported API Client Methods
// ==============================================================================

/**
 * GET /api/health
 * Checks overall backend operational health.
 */
export async function getHealth(): Promise<HealthResponse> {
  const url = `${getApiBaseUrl()}/api/health`;
  const response = await fetchWithTimeout(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    timeoutMs: 5000,
  });
  return handleResponse<HealthResponse>(response);
}

/**
 * GET /api/model/status
 * Queries the state and performance metrics of the computer vision model.
 */
export async function getModelStatus(): Promise<ModelStatusResponse> {
  const url = `${getApiBaseUrl()}/api/model/status`;
  const response = await fetchWithTimeout(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    timeoutMs: 5000,
  });
  return handleResponse<ModelStatusResponse>(response);
}

/**
 * POST /api/scans
 * Submits an image for computer vision recycling classification.
 * Uses a 30-second timeout to allow for model inference and cold starts.
 */
export async function submitScan(file: File | Blob): Promise<ScanClassificationResponse> {
  const url = `${getApiBaseUrl()}/api/scans`;
  const formData = new FormData();
  formData.append("file", file, file instanceof File ? file.name : "camera-capture.jpg");

  const response = await fetchWithTimeout(url, {
    method: "POST",
    body: formData,
    headers: {
      Accept: "application/json",
    },
    timeoutMs: 30000, // 30s timeout for vision model inference
  });

  return handleResponse<ScanClassificationResponse>(response);
}

/**
 * POST /api/materials/confirm
 * Submits confirmed item classification to be committed to the Digital Twin inventory.
 * Requires an idempotency key to prevent accidental duplicate additions on retry.
 */
/**
 * POST /api/scans/preview
 * Runs single-image classification for live camera feedback without creating a pending scan.
 */
export async function previewScan(file: File | Blob): Promise<ScanPreviewResponse> {
  const url = `${getApiBaseUrl()}/api/scans/preview`;
  const formData = new FormData();
  formData.append("file", file, file instanceof File ? file.name : "camera-preview.jpg");

  const response = await fetchWithTimeout(url, {
    method: "POST",
    body: formData,
    headers: { Accept: "application/json" },
    timeoutMs: 30000,
  });
  return handleResponse<ScanPreviewResponse>(response);
}
export async function confirmScan(
  scanId: string,
  payload: ScanConfirmationRequest
): Promise<ScanConfirmationResponse> {
  if (!scanId) {
    throw new ApiError("Scan ID is required for confirmation.", 400, "MISSING_SCAN_ID");
  }

  const url = `${getApiBaseUrl()}/api/materials/confirm`;
  const response = await fetchWithTimeout(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(payload.idempotency_key
        ? { "Idempotency-Key": payload.idempotency_key }
        : {}),
    },
    body: JSON.stringify({ ...payload, scan_id: scanId }),
    timeoutMs: 15000,
  });

  const result = await handleResponse<ScanConfirmationResponse>(response);
  if (
    response.status !== 201 ||
    !result ||
    typeof result.id !== "string" ||
    result.scan_id !== scanId ||
    typeof result.confirmed_category !== "string"
  ) {
    throw new ApiError(
      "The backend did not return a valid persisted material confirmation.",
      response.status,
      "INVALID_CONFIRMATION_RESPONSE"
    );
  }
  return result;
}

/**
 * GET /api/model/detector/status
 * Readiness and licence information for the mixed-waste object detector.
 */
export async function getDetectorStatus(): Promise<DetectorStatusResponse> {
  const url = `${getApiBaseUrl()}/api/model/detector/status`;
  const response = await fetchWithTimeout(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    timeoutMs: 5000,
  });
  return handleResponse<DetectorStatusResponse>(response);
}

/**
 * POST /api/scans/batch
 * Detects and analyses every waste object in one mixed-waste image.
 *
 * A successful response with zero items is a genuine empty detection result, not
 * an error, and callers must render it as such. No inventory changes here: each
 * returned item is a pending scan that must be confirmed separately.
 */
export async function submitBatchScan(
  file: File | Blob,
  source: "upload" | "camera" = "upload"
): Promise<BatchScanResponse> {
  const url = `${getApiBaseUrl()}/api/scans/batch`;
  const formData = new FormData();
  formData.append("file", file, file instanceof File ? file.name : "mixed-scene.jpg");
  formData.append("source", source);

  const response = await fetchWithTimeout(url, {
    method: "POST",
    body: formData,
    headers: {
      Accept: "application/json",
    },
    timeoutMs: 45000, // Detector inference plus a per-item crop cross-check
  });

  return handleResponse<BatchScanResponse>(response);
}

/**
 * POST /api/materials/confirm-batch
 * Commits reviewed items, one item at a time, through the single-item workflow.
 *
 * Partial outcomes are normal. Callers must read `failed_count` and each
 * result's status rather than treating HTTP 200 as a complete success.
 */
export async function confirmBatch(payload: BatchConfirmRequest): Promise<BatchConfirmResponse> {
  if (!payload.items || payload.items.length === 0) {
    throw new ApiError("Select at least one item before confirming.", 400, "EMPTY_BATCH");
  }

  const url = `${getApiBaseUrl()}/api/materials/confirm-batch`;
  const response = await fetchWithTimeout(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
    timeoutMs: 30000,
  });

  const result = await handleResponse<BatchConfirmResponse>(response);
  if (
    !result ||
    !Array.isArray(result.results) ||
    typeof result.confirmed_count !== "number" ||
    typeof result.failed_count !== "number"
  ) {
    throw new ApiError(
      "The backend did not return a valid batch confirmation result.",
      response.status,
      "INVALID_BATCH_CONFIRMATION_RESPONSE"
    );
  }
  return result;
}

/**
 * GET /api/twin/snapshot
 * Retrieves the current state of Digital Twin material inventory and bins.
 */
export async function getTwinSnapshot(): Promise<DigitalTwinSnapshot> {
  const url = `${getApiBaseUrl()}/api/twin/snapshot`;
  const response = await fetchWithTimeout(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    timeoutMs: 10000,
  });
  return handleResponse<DigitalTwinSnapshot>(response);
}

/**
 * GET /api/events
 * Retrieves recent scan and routing events for timeline tracking.
 */
export async function getEvents(limit = 50): Promise<EventHistoryResponse> {
  const url = `${getApiBaseUrl()}/api/events?limit=${encodeURIComponent(limit)}`;
  const response = await fetchWithTimeout(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    timeoutMs: 10000,
  });
  return handleResponse<EventHistoryResponse>(response);
}

/**
 * GET /api/recommendations
 * Retrieves active generative recommendations grounded in current Twin inventory.
 */
export async function getRecommendations(): Promise<RecommendationsResponse> {
  const url = `${getApiBaseUrl()}/api/recommendations`;
  const response = await fetchWithTimeout(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    timeoutMs: 10000,
  });
  return handleResponse<RecommendationsResponse>(response);
}

/**
 * POST /api/recommendations/generate
 * Triggers backend synthesis of fresh recommendations based on the latest inventory.
 */
export async function generateRecommendations(
  payload?: GenerateRecommendationsRequest
): Promise<RecommendationItem> {
  const url = `${getApiBaseUrl()}/api/recommendations/generate`;
  const response = await fetchWithTimeout(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: payload ? JSON.stringify(payload) : "{}",
    timeoutMs: 25000,
  });
  return handleResponse<RecommendationItem>(response);
}

/**
 * POST /api/agent/message
 * Submits an operational query to the backend Recycling Intelligence Agent.
 */
export async function sendAgentMessage(
  payload: AgentMessageRequest
): Promise<AgentMessageResponse> {
  const url = `${getApiBaseUrl()}/api/agent/message`;
  const response = await fetchWithTimeout(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
    timeoutMs: 35000,
  });
  return handleResponse<AgentMessageResponse>(response);
}

/**
 * GET /api/agent/status
 * Retrieves operational status of the Recycling Intelligence Agent.
 */
export async function getAgentStatus(): Promise<AgentStatusResponse> {
  const url = `${getApiBaseUrl()}/api/agent/status`;
  const response = await fetchWithTimeout(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    timeoutMs: 10000,
  });
  return handleResponse<AgentStatusResponse>(response);
}
