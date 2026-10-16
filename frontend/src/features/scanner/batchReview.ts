/**
 * ==============================================================================
 * Smart Recycling Agent — Mixed-Waste Batch Presentation Helpers
 * ==============================================================================
 * Pure helpers shared by the batch review screen.
 *
 * These are deliberately free of React so the box geometry and the review-reason
 * wording can be reasoned about and inspected on their own. No accuracy or
 * correctness claim is made anywhere here: reason labels describe why a human is
 * being asked, and the box math only maps stored coordinates onto a rendered
 * image.
 * ==============================================================================
 */

import { DetectionBox } from "@/types/api";

/**
 * Human-readable explanation for each backend review reason.
 *
 * These strings must stay faithful to the backend rule that produced them. A
 * reason that understates its cause (for example presenting a featureless-region
 * flag as a confidence issue) would mislead the reviewer.
 */
export const REVIEW_REASON_LABELS: Record<string, string> = {
  low_detection_score: "Detector score is below the review threshold.",
  unsupported_material_class:
    "The detector could not establish a specific material for this object.",
  unsupported_destination:
    "No material bin accepts this item, so it can only be held for review.",
  ambiguous_material_confidence:
    "Two visually confusable materials scored almost equally here.",
  overlapping_material_conflict:
    "The detector reported more than one material for this same region.",
  featureless_crop_region:
    "This region has almost no visual texture, so it may not be an object at all.",
  cross_check_disagreement:
    "The independent single-item classifier disagreed with the detector.",
};

/** Turn raw reason codes into sentences, keeping unknown codes visible. */
export function describeReviewReasons(reasons: string[]): string[] {
  return reasons.map((reason) => {
    const known = REVIEW_REASON_LABELS[reason];
    if (known) return known;
    // Surface an unrecognised code rather than hiding it from the reviewer.
    return `Unrecognised review reason from the backend: ${reason.replace(/_/g, " ")}.`;
  });
}

export interface BoxStyle {
  left: string;
  top: string;
  width: string;
  height: string;
}

/**
 * Convert a stored detection box into CSS percentages.
 *
 * Percentages are used rather than pixels so the overlay stays aligned when the
 * image is scaled to fit a responsive container. Coordinates are clamped to the
 * image bounds, which keeps a box from spilling outside the picture if a stored
 * value is ever slightly out of range.
 */
export function boxToPercentStyle(box: DetectionBox): BoxStyle {
  const clamp = (value: number) => Math.max(0, Math.min(1, value));
  const left = clamp(box.normalized_x1);
  const top = clamp(box.normalized_y1);
  const right = clamp(box.normalized_x2);
  const bottom = clamp(box.normalized_y2);

  return {
    left: `${left * 100}%`,
    top: `${top * 100}%`,
    width: `${Math.max(0, right - left) * 100}%`,
    height: `${Math.max(0, bottom - top) * 100}%`,
  };
}

/** A short label for an item, e.g. "Plastic 90%". */
export function formatItemScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

/**
 * Summarise a batch outcome without overstating it.
 *
 * Returns the wording for the result banner. A partial outcome is described as
 * partial, never as success.
 */
export function describeBatchOutcome(
  confirmedCount: number,
  alreadyConfirmedCount: number,
  failedCount: number
): string {
  const accepted = confirmedCount + alreadyConfirmedCount;
  if (failedCount === 0) {
    if (alreadyConfirmedCount === 0) {
      return `Recorded ${confirmedCount} item${confirmedCount === 1 ? "" : "s"} in the Digital Twin.`;
    }
    return `Recorded ${confirmedCount} new item${confirmedCount === 1 ? "" : "s"}; ${alreadyConfirmedCount} had already been recorded.`;
  }
  return `Partial result: ${accepted} item${accepted === 1 ? "" : "s"} recorded, ${failedCount} could not be recorded. See the failed items below.`;
}
