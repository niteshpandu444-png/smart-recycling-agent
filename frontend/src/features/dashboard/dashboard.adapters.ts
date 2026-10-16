import {
  DigitalTwinSnapshot,
  EventHistoryResponse,
  EventItem,
  RecommendationItem,
} from "@/types/api";
import {
  DashboardBin,
  DashboardEvent,
  DashboardMaterialCategory,
  DashboardOverviewMetrics,
  DashboardRecommendation,
  MaterialFlowNode,
} from "./dashboard.types";

/** The dashboard groups material-specific backend categories into its visual streams. */
export function toDashboardCategory(category: string | null | undefined): DashboardMaterialCategory {
  switch (category?.toLowerCase()) {
    case "plastic":
    case "paper":
    case "metal":
    case "glass":
    case "recyclable":
      return "recyclable";
    case "organic":
    case "compostable":
    case "biodegradable":
      return "biodegradable";
    case "reusable":
      return "reusable";
    case "hazardous":
      return "hazardous";
    default:
      return "unknown";
  }
}

export function adaptSnapshot(snapshot: DigitalTwinSnapshot): {
  metrics: DashboardOverviewMetrics;
  bins: DashboardBin[];
} {
  const groupedInventory = new Map<DashboardMaterialCategory, number>();
  for (const [category, quantity] of Object.entries(snapshot.category_inventory)) {
    const visualCategory = toDashboardCategory(category);
    groupedInventory.set(visualCategory, (groupedInventory.get(visualCategory) ?? 0) + quantity);
  }

  const totalInventory = Array.from(groupedInventory.values()).reduce((sum, value) => sum + value, 0);

  // Detected (batch) items are grouped the same way but reported separately, so
  // batch activity can never be read as confirmed inventory.
  const groupedDetections = new Map<DashboardMaterialCategory, number>();
  for (const [category, count] of Object.entries(snapshot.detected_item_totals ?? {})) {
    const visualCategory = toDashboardCategory(category);
    groupedDetections.set(visualCategory, (groupedDetections.get(visualCategory) ?? 0) + count);
  }

  const metrics: DashboardOverviewMetrics = {
    totalConfirmedItems: snapshot.total_confirmed_items,
    activeRoutesCount: snapshot.bins.length,
    pendingVerificationCount: snapshot.pending_verification_count,
    snapshotTimestamp: snapshot.timestamp,
    categoryBreakdown: Array.from(groupedInventory, ([category, count]) => ({
      category,
      count,
      unit: "recorded units",
      percentageOfTotal: totalInventory > 0 ? (count / totalInventory) * 100 : 0,
    })),
    batchScanCount: snapshot.batch_scan_count ?? 0,
    detectedItemCount: Object.values(snapshot.detected_item_totals ?? {}).reduce(
      (sum, value) => sum + value,
      0
    ),
    needsReviewScanCount: snapshot.needs_review_scan_count ?? 0,
    confirmedFromBatchCount: snapshot.confirmed_from_batch_count ?? 0,
    detectedCategoryBreakdown: Array.from(groupedDetections, ([category, count]) => ({
      category,
      count,
    })),
    recentBatches: (snapshot.recent_batch_activity ?? []).map((batch) => ({
      batchId: batch.batch_id,
      createdAt: batch.created_at,
      detectionCount: batch.detection_count,
      reviewRequiredCount: batch.review_required_count,
      confirmedCount: batch.confirmed_count,
      pendingReviewCount: batch.pending_review_count,
    })),
  };

  const bins: DashboardBin[] = snapshot.bins.map((bin) => ({
    id: bin.id,
    name: bin.name,
    category: toDashboardCategory(bin.accepted_category),
    currentInventory: bin.current_inventory,
    capacity: bin.capacity,
    inventoryUnit: bin.inventory_unit,
    occupancyPercentage: bin.occupancy_percentage,
    status: ["normal", "warning", "critical", "maintenance"].includes(bin.status)
      ? (bin.status as DashboardBin["status"])
      : "unknown",
    contaminationRisk: bin.contamination_risk,
  }));

  return { metrics, bins };
}

function eventItemName(event: EventItem): string {
  const payload = event.payload ?? {};
  for (const key of ["item_name", "description", "name"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return event.affected_category ?? event.event_type.replace(/_/g, " ");
}

export function adaptEvents(response: EventHistoryResponse, bins: DashboardBin[]): DashboardEvent[] {
  const binNames = new Map(bins.map((bin) => [bin.id, bin.name]));
  return response.items.map((event) => {
    const destinationId = event.destination_bin_id ?? "Unassigned";
    return {
      id: event.id,
      eventType: event.event_type,
      itemName: eventItemName(event),
      category: toDashboardCategory(event.affected_category),
      destinationId,
      destinationName: binNames.get(destinationId),
      quantity: event.quantity,
      unit: event.unit,
      timestamp: event.timestamp,
      processingStatus: event.event_type === "reversal" ? "reversed" : "completed",
      metadata: event.payload ?? undefined,
    };
  });
}

export function eventsToMaterialFlows(events: DashboardEvent[]): MaterialFlowNode[] {
  const totalQuantity = events.reduce((sum, event) => sum + Math.max(0, event.quantity), 0);
  return events.map((event) => ({
    id: event.id,
    label: event.category === "unknown" ? event.itemName : `${event.category} material`,
    category: event.category,
    quantity: event.quantity,
    unit: event.unit,
    targetBinId: event.destinationId,
    targetBinName: event.destinationName,
    flowSharePercentage: totalQuantity > 0 ? (event.quantity / totalQuantity) * 100 : 0,
    dataOrigin: "observed",
  }));
}

export function adaptRecommendations(items: RecommendationItem[]): DashboardRecommendation[] {
  return items.map((item) => ({
    id: item.id,
    title: item.title,
    description: item.recommendation_text,
    createdAt: item.created_at,
    generationMethod: item.generation_method,
    supportingData: item.supporting_data,
    status: item.status,
  }));
}
