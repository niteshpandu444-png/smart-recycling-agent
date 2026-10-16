/**
 * ==============================================================================
 * Smart Recycling Agent — Digital Twin Dashboard Types
 * ==============================================================================
 * Feature-local presentation interfaces for the Digital Twin Dashboard.
 *
 * NOTE: These interfaces are decoupled from any remote or speculative imports.
 * They define the contract required by dashboard presentation components
 * (bins, flow diagrams, metrics, audit events, and AI recommendations).
 *
 * When integrated with the shared frontend foundation (origin/feat/frontend-scanner-foundation),
 * adapter functions in INTEGRATION.md map the shared API schemas to these types.
 * ==============================================================================
 */

/**
 * Standard classification categories recognized across the recycling system.
 */
export type DashboardMaterialCategory =
  | "recyclable"
  | "reusable"
  | "biodegradable"
  | "hazardous"
  | "unknown"
  | string;

/**
 * Visual badge distinction for observed vs calculated vs virtual state.
 */
export type DataOrigin = "observed" | "calculated" | "virtual";

/**
 * Status level for bins based on occupancy, risk, or maintenance flags.
 */
export type BinOperationalStatus =
  | "normal"
  | "warning"
  | "critical"
  | "maintenance"
  | "unknown"
  | string;

/**
 * View model representing a physical or virtual destination bin.
 */
export interface DashboardBin {
  /** Unique bin identifier (e.g., 'bin_metals_01', 'bin-plastic') */
  id: string;
  /** Human-readable bin title (e.g., 'Metals & Aluminum', 'Plastics') */
  name: string;
  /** Primary accepted material category */
  category: DashboardMaterialCategory;
  /** Current quantity stored in the bin */
  currentInventory: number;
  /** Configured capacity of the bin. If undefined or <= 0, capacity is unconfigured. */
  capacity?: number | null;
  /** Unit of measurement (e.g. 'kg', 'items', 'liters') */
  inventoryUnit: string;
  /**
   * Occupancy percentage (0.0 to 100.0+).
   * Null if capacity is unconfigured or incompatible with inventory unit.
   */
  occupancyPercentage?: number | null;
  /** Current operational status */
  status: BinOperationalStatus;
  /** Simulated contamination risk factor (0.0 to 1.0) if reported by backend */
  contaminationRisk?: number | null;
  /** ISO timestamp of last update or sensor report */
  lastUpdated?: string | null;
  /** Whether this bin is currently flagged for service or inspection */
  needsService?: boolean;
}

/**
 * Node in the material flow visualization.
 */
export interface MaterialFlowNode {
  id: string;
  label: string;
  category: DashboardMaterialCategory;
  /** Total volume or items moving through this flow */
  quantity: number;
  unit: string;
  /** Destination bin or route identifier */
  targetBinId?: string;
  targetBinName?: string;
  /** Derived percentage of total material flow (0.0 to 100.0) */
  flowSharePercentage?: number;
  /** Origin distinction */
  dataOrigin: DataOrigin;
}

/**
 * One mixed-waste scene scan and how its items were resolved.
 *
 * `detectionCount` counts detected objects, while `confirmedCount` counts the
 * subset a user actually confirmed into inventory. The gap between them is the
 * point of showing both: a detection is not a confirmed item.
 */
export interface DashboardBatchActivity {
  batchId: string;
  createdAt: string;
  detectionCount: number;
  reviewRequiredCount: number;
  /** Detected items confirmed into inventory. */
  confirmedCount: number;
  /** Detected items still flagged for review. */
  pendingReviewCount: number;
}

/**
 * Cumulative metrics and processing summaries.
 */
export interface DashboardOverviewMetrics {
  /** Total confirmed items recorded by the Digital Twin (observed) */
  totalConfirmedItems: number;
  /** Number of active destination routes/bins (observed) */
  activeRoutesCount: number;
  /** Number of items awaiting manual verification (observed) */
  pendingVerificationCount?: number;
  /** Breakdown of inventory or throughput per material category */
  categoryBreakdown: {
    category: DashboardMaterialCategory;
    count: number;
    unit: string;
    percentageOfTotal: number;
  }[];
  /** ISO timestamp of snapshot */
  snapshotTimestamp: string;
  /** Mixed-waste batch activity. These count detected items, never inventory. */
  batchScanCount?: number;
  detectedItemCount?: number;
  needsReviewScanCount?: number;
  confirmedFromBatchCount?: number;
  detectedCategoryBreakdown?: { category: DashboardMaterialCategory; count: number }[];
  recentBatches?: DashboardBatchActivity[];
}

/**
 * Event processing and audit log item.
 */
export interface DashboardEvent {
  id: string;
  /** Standard event types: scan_confirmed, route_updated, threshold_alert, etc. */
  eventType: string;
  /** Item description or name (e.g. 'Aluminum Beverage Can') */
  itemName: string;
  /** Material category */
  category: DashboardMaterialCategory;
  /** Destination bin ID */
  destinationId: string;
  /** Human-friendly destination label if known */
  destinationName?: string;
  /** Quantity added, modified, or transferred */
  quantity: number;
  unit: string;
  /** ISO-8601 timestamp */
  timestamp: string;
  /** Processing outcome */
  processingStatus: "completed" | "pending" | "failed" | "reversed" | string;
  /** Optional metadata details */
  metadata?: Record<string, unknown>;
}

/**
 * AI / Generative recommendation view model.
 */
export interface DashboardRecommendation {
  id: string;
  title: string;
  description: string;
  /** Present only when the backend supplies an explicit severity. */
  severity?: "low" | "medium" | "high" | "critical" | string;
  /** Present only when the backend supplies an explicit action type. */
  actionType?: string;
  createdAt: string;
  /** Generation source: 'llm' | 'deterministic' | 'rule_based' */
  generationMethod?: string;
  /** Supporting capacity snapshot or sensor telemetry */
  supportingData?: Record<string, unknown>;
  /** Recommendation lifecycle status */
  status?: "new" | "acknowledged" | "dismissed" | "resolved" | string;
}

/**
 * Dashboard connection and sync states.
 */
export type DashboardConnectionState =
  | "connected"
  | "reconnecting"
  | "offline"
  | "stale"
  | "unavailable";

/** Availability of the REST endpoints used to load dashboard data. */
export type DashboardRestApiState = "checking" | "available" | "unavailable";

/**
 * Top-level view model passed to the main DashboardView presentation component.
 */
export interface DashboardViewProps {
  /** Overall metrics summary */
  metrics?: DashboardOverviewMetrics | null;
  /** Virtual destination bins */
  bins?: DashboardBin[];
  /** Material flow nodes */
  materialFlows?: MaterialFlowNode[];
  /** Recent audit/processing events */
  events?: DashboardEvent[];
  /** Backend AI recommendations */
  recommendations?: DashboardRecommendation[];
  /** WebSocket connection state. */
  connectionState: DashboardConnectionState;
  /** Availability of the REST endpoints used to load dashboard data. */
  restApiState: DashboardRestApiState;
  /** ISO timestamp of last successful sync with backend */
  lastSyncTimestamp?: string | null;
  /** Loading flag during initial fetch or manual refresh */
  isLoading?: boolean;
  /** Error message if fetch failed */
  errorMessage?: string | null;
  /** Callback for manual refresh */
  onRefresh?: () => void;
  /**
   * Callback to trigger on-demand AI recommendation generation.
   * If omitted, generation button renders with explanatory notice.
   */
  onGenerateRecommendations?: () => Promise<void> | void;
  /** Flag indicating recommendation generation is currently in-flight */
  isGeneratingRecommendations?: boolean;
}
