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
  ScanClassificationResponse,
  ScanConfirmationRequest,
  ScanConfirmationResponse,
  DigitalTwinSnapshot,
  EventHistoryResponse,
  RecommendationsResponse,
  GenerateRecommendationsRequest,
  ApiErrorResponse,
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
  if (envUrl && envUrl.trim().length > 0) {
    return envUrl.replace(/\/+$/, "");
  }
  return "http://localhost:8000";
}

/**
 * Generates an RFC4122 v4 UUID or secure fallback string for idempotency keys.
 */
export function generateIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Safe fallback if crypto.randomUUID is not supported in environment
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
      const messages = fastapiDetail.map((d: any) => d.msg || JSON.stringify(d)).join("; ");
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
 * POST /api/scans/{id}/confirm
 * Submits confirmed item classification to be committed to the Digital Twin inventory.
 * Requires an idempotency key to prevent accidental duplicate additions on retry.
 */
export async function confirmScan(
  scanId: string,
  payload: ScanConfirmationRequest
): Promise<ScanConfirmationResponse> {
  if (!scanId) {
    throw new ApiError("Scan ID is required for confirmation.", 400, "MISSING_SCAN_ID");
  }

  const url = `${getApiBaseUrl()}/api/scans/${encodeURIComponent(scanId)}/confirm`;
  const response = await fetchWithTimeout(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "Idempotency-Key": payload.idempotency_key,
    },
    body: JSON.stringify(payload),
    timeoutMs: 15000,
  });

  return handleResponse<ScanConfirmationResponse>(response);
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
): Promise<RecommendationsResponse> {
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
  return handleResponse<RecommendationsResponse>(response);
}
