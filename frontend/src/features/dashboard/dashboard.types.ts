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
  | "unknown";

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
  | "unknown";

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
  severity: "low" | "medium" | "high" | "critical";
  actionType: "empty_bin" | "reroute" | "material_reuse" | "maintenance" | string;
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
  /** Current connection / backend health state */
  connectionState: DashboardConnectionState;
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
