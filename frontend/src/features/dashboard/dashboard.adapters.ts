import type {
  DigitalTwinSnapshot,
  EventItem,
  RecommendationItem,
} from "@/types/api";
import type {
  DashboardBin,
  DashboardEvent,
  DashboardMaterialCategory,
  DashboardOverviewMetrics,
  DashboardRecommendation,
  MaterialFlowNode,
} from "./dashboard.types";

const KNOWN_CATEGORIES = new Set([
  "recyclable",
  "reusable",
  "biodegradable",
  "hazardous",
  "plastic",
  "paper",
  "metal",
  "glass",
  "organic",
  "compostable",
  "holding",
]);

export function adaptCategory(value: string | null | undefined): DashboardMaterialCategory {
  if (!value) return "unknown";
  const normalized = value.trim().toLowerCase();
  return KNOWN_CATEGORIES.has(normalized) ? normalized : value;
}

function adaptBinStatus(value: string): DashboardBin["status"] {
  switch (value.toLowerCase()) {
    case "normal":
      return "normal";
    case "warning":
      return "warning";
    case "critical":
      return "critical";
    case "maintenance":
      return "maintenance";
    default:
      return "unknown";
  }
}

export function adaptSnapshot(snapshot: DigitalTwinSnapshot): {
  metrics: DashboardOverviewMetrics;
  bins: DashboardBin[];
  materialFlows: MaterialFlowNode[];
} {
  const inventory = Object.entries(snapshot.category_inventory);
  const categoryTotal = inventory.reduce((total, [, quantity]) => total + quantity, 0);

  return {
    metrics: {
      totalConfirmedItems: snapshot.total_confirmed_items,
      activeRoutesCount: snapshot.bins.length,
      pendingVerificationCount: snapshot.pending_verification_count,
      categoryBreakdown: inventory.map(([category, quantity]) => ({
        category: adaptCategory(category),
        count: quantity,
        unit: "recorded quantity",
        percentageOfTotal: categoryTotal > 0 ? (quantity / categoryTotal) * 100 : 0,
      })),
      snapshotTimestamp: snapshot.timestamp,
    },
    bins: snapshot.bins.map((bin) => ({
      id: bin.id,
      name: bin.name,
      category: adaptCategory(bin.accepted_category),
      currentInventory: bin.current_inventory,
      capacity: bin.capacity,
      inventoryUnit: bin.inventory_unit,
      occupancyPercentage: bin.occupancy_percentage,
      status: adaptBinStatus(bin.status),
      contaminationRisk: bin.contamination_risk,
    })),
    // Inventory aggregates do not identify material movement or routes.
    materialFlows: [],
  };
}

export function adaptEvents(items: EventItem[], snapshot?: DigitalTwinSnapshot | null): DashboardEvent[] {
  const binNames = new Map<string, string>(
    (snapshot?.bins ?? []).map((bin) => [bin.id, bin.name] as const),
  );

  return items.map((item) => {
    const payload = item.payload ?? {};
    const payloadName = payload.description;
    const category = adaptCategory(item.affected_category);
    const destinationId = item.destination_bin_id ?? item.source_bin_id ?? "";

    return {
      id: item.id,
      eventType: item.event_type,
      itemName: typeof payloadName === "string" && payloadName.trim()
        ? payloadName
        : item.affected_category ?? item.event_type.replace(/_/g, " "),
      category,
      destinationId,
      destinationName: binNames.get(destinationId),
      quantity: item.quantity,
      unit: item.unit,
      timestamp: item.timestamp,
      processingStatus: item.event_type === "reversal" || item.event_type === "event_reversed"
        ? "reversed"
        : "not_reported",
      metadata: payload,
    };
  });
}

export function adaptRecommendation(item: RecommendationItem): DashboardRecommendation {
  return {
    id: item.id,
    title: item.title,
    description: item.recommendation_text,
    severity: "unknown",
    createdAt: item.created_at,
    generationMethod: item.generation_method,
    supportingData: item.supporting_data,
    status: item.status,
  };
}

export function adaptRecommendations(items: RecommendationItem[]): DashboardRecommendation[] {
  return items.map(adaptRecommendation);
}
