"use client";

import React from "react";
import { BatchScanItem, MaterialCategory } from "@/types/api";
import { boxToPercentStyle, formatItemScore } from "./batchReview";
import { AlertTriangle } from "lucide-react";

/**
 * Colours used to draw a detection over a photograph.
 *
 * Hex values are used instead of the Tailwind chip classes because a box has to
 * stay legible over arbitrary image content, and the chip palette is tuned for
 * flat card backgrounds.
 */
const OVERLAY_COLORS: Record<string, string> = {
  plastic: "#10b981",
  paper: "#0ea5e9",
  metal: "#f59e0b",
  glass: "#f43f5e",
  organic: "#84cc16",
  biodegradable: "#84cc16",
  compostable: "#84cc16",
  holding: "#94a3b8",
  hazardous: "#e11d48",
  reusable: "#6366f1",
};

const FALLBACK_COLOR = "#94a3b8";

export function overlayColorFor(category: MaterialCategory | string): string {
  return OVERLAY_COLORS[category] ?? FALLBACK_COLOR;
}

interface DetectionOverlayProps {
  items: BatchScanItem[];
  selectedItemId: string | null;
  onSelectItem: (itemId: string) => void;
  /** Items the reviewer has removed from the batch; drawn struck through. */
  excludedItemIds: string[];
  categoryByItemId: Record<string, MaterialCategory>;
}

/**
 * Absolutely-positioned detection boxes over the scan image.
 *
 * Boxes use percentage geometry derived from the backend's normalized
 * coordinates, so they stay aligned with the picture at any rendered size. The
 * container is responsible for matching the source aspect ratio.
 */
export const DetectionOverlay: React.FC<DetectionOverlayProps> = ({
  items,
  selectedItemId,
  onSelectItem,
  excludedItemIds,
  categoryByItemId,
}) => {
  return (
    <div className="absolute inset-0">
      {items.map((item, index) => {
        const category = categoryByItemId[item.item_id] ?? item.category;
        const color = overlayColorFor(category);
        const isSelected = selectedItemId === item.item_id;
        const isExcluded = excludedItemIds.includes(item.item_id);
        const needsReview = item.review_status === "needs_review";

        return (
          <button
            key={item.item_id}
            type="button"
            onClick={() => onSelectItem(item.item_id)}
            aria-pressed={isSelected}
            aria-label={`Detection ${index + 1}: ${category}, score ${formatItemScore(
              item.score
            )}${needsReview ? ", needs review" : ""}${isExcluded ? ", removed from this batch" : ""}`}
            style={{
              ...boxToPercentStyle(item.box),
              borderColor: color,
              backgroundColor: isExcluded ? "rgba(148,163,184,0.12)" : `${color}1f`,
              borderStyle: needsReview ? "dashed" : "solid",
              opacity: isExcluded ? 0.45 : 1,
            }}
            className={`absolute border-2 transition-all ${
              isSelected ? "ring-2 ring-white dark:ring-slate-900 shadow-lg z-10" : "z-0"
            }`}
          >
            <span
              className="absolute -top-0.5 left-0 flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-semibold text-white rounded-br-md whitespace-nowrap"
              style={{
                backgroundColor: color,
                textDecoration: isExcluded ? "line-through" : "none",
              }}
            >
              {needsReview && <AlertTriangle className="w-2.5 h-2.5" />}
              {index + 1}. {category} {formatItemScore(item.score)}
            </span>
          </button>
        );
      })}
    </div>
  );
};
