"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import {
  BatchConfirmRequest,
  BatchConfirmResponse,
  BatchScanResponse,
  MaterialCategory,
} from "@/types/api";
import { generateIdempotencyKey, ApiError } from "@/lib/api";
import { ALL_CATEGORIES, CATEGORY_STYLES } from "./ClassificationCard";
import { DetectionOverlay } from "./DetectionOverlay";
import { describeBatchOutcome, describeReviewReasons, formatItemScore } from "./batchReview";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCircle2,
  Info,
  Layers,
  RefreshCw,
  RotateCcw,
  ScanLine,
  Send,
  Trash2,
} from "lucide-react";

interface BatchScanViewProps {
  imageFile: File;
  result: BatchScanResponse;
  /** Commits the reviewed items; resolves with the backend's per-item outcome. */
  onSubmit: (request: BatchConfirmRequest) => Promise<BatchConfirmResponse>;
  onScanAnother: () => void;
}

export const BatchScanView: React.FC<BatchScanViewProps> = ({
  imageFile,
  result,
  onSubmit,
  onScanAnother,
}) => {
  const [categoryByItemId, setCategoryByItemId] = useState<Record<string, MaterialCategory>>(
    () =>
      result.items.reduce<Record<string, MaterialCategory>>((accumulator, item) => {
        accumulator[item.item_id] = item.category;
        return accumulator;
      }, {})
  );
  const [excludedItemIds, setExcludedItemIds] = useState<string[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(
    result.items.length > 0 ? result.items[0].item_id : null
  );
  const [showNotes, setShowNotes] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<BatchConfirmResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  /** Stable per (item, category) keys: retries reuse them, corrections get new ones. */
  const idempotencyKeysRef = useRef<Map<string, string>>(new Map());
  const lastRequestRef = useRef<BatchConfirmRequest | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(imageFile);
    setImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [imageFile]);

  const keyFor = (itemId: string, category: MaterialCategory): string => {
    const mapKey = `${itemId}:${category}`;
    const existing = idempotencyKeysRef.current.get(mapKey);
    if (existing) return existing;
    const generated = generateIdempotencyKey();
    idempotencyKeysRef.current.set(mapKey, generated);
    return generated;
  };

  const includedItems = useMemo(
    () => result.items.filter((item) => !excludedItemIds.includes(item.item_id)),
    [result.items, excludedItemIds]
  );
  const reviewCount = result.items.filter((item) => item.review_status === "needs_review").length;

  const buildRequest = (): BatchConfirmRequest => ({
    batch_id: result.batch_id,
    items: includedItems.map((item) => {
      const category = categoryByItemId[item.item_id] ?? item.category;
      return {
        scan_id: item.scan_id,
        item_id: item.item_id,
        confirmed_category: category,
        // Accepting the detector's own label is a different provenance claim from
        // a human-corrected one, and the backend records them separately.
        confirmation_source: category === item.category ? "model_accepted" : "user_corrected",
        idempotency_key: keyFor(item.item_id, category),
      };
    }),
  });

  const submit = async (request: BatchConfirmRequest) => {
    setIsSubmitting(true);
    setSubmitError(null);
    lastRequestRef.current = request;
    try {
      const response = await onSubmit(request);
      setOutcome(response);
    } catch (error) {
      setSubmitError(
        error instanceof ApiError
          ? error.message
          : "Could not record these items in the Digital Twin. Retrying reuses the same keys, so no item is counted twice."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleConfirm = () => {
    if (includedItems.length === 0) return;
    void submit(buildRequest());
  };

  const handleRetry = () => {
    if (lastRequestRef.current) {
      void submit(lastRequestRef.current);
    }
  };

  const toggleExcluded = (itemId: string) => {
    setSelectedItemId(itemId);
    setExcludedItemIds((previous) =>
      previous.includes(itemId)
        ? previous.filter((value) => value !== itemId)
        : [...previous, itemId]
    );
  };

  const aspectRatio =
    result.image_width > 0 && result.image_height > 0
      ? `${result.image_width} / ${result.image_height}`
      : "4 / 3";

  // -------------------------------------------------------------------------
  // Empty detection result: reported as a real outcome, never padded out.
  // -------------------------------------------------------------------------
  if (result.items.length === 0) {
    return (
      <div className="flex flex-col w-full max-w-md mx-auto bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-md p-5">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 flex items-center justify-center shrink-0">
            <ScanLine className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              No items detected
            </h2>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              No inventory was changed and nothing was recorded.
            </p>
          </div>
        </div>

        <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed mb-3">
          The detector found no waste objects above its operating threshold in this image. This is an
          empty detection result, not a classification of the whole picture. Try a closer, brighter
          photo with items clearly separated.
        </p>

        <ul className="space-y-1.5 mb-4">
          {result.notes.map((note) => (
            <li key={note} className="flex items-start gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{note}</span>
            </li>
          ))}
        </ul>

        <button
          type="button"
          onClick={onScanAnother}
          className="w-full min-h-[44px] py-3 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold flex items-center justify-center gap-2 active:scale-98 transition-all shadow-md"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Scan Another Scene
        </button>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Recorded outcome
  // -------------------------------------------------------------------------
  if (outcome) {
    const failedResults = outcome.results.filter((entry) => entry.status === "failed");
    return (
      <div className="flex flex-col w-full max-w-md mx-auto bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-md p-5">
        <div className="flex items-center gap-2.5 mb-3">
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
              failedResults.length > 0
                ? "bg-amber-100 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400"
                : "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400"
            }`}
          >
            {failedResults.length > 0 ? (
              <AlertTriangle className="w-5 h-5" />
            ) : (
              <CheckCircle2 className="w-5 h-5" />
            )}
          </div>
          <div>
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              {failedResults.length > 0 ? "Partially recorded" : "Batch recorded"}
            </h2>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              Digital Twin inventory updated for accepted items only.
            </p>
          </div>
        </div>

        <p
          className={`text-xs leading-relaxed mb-4 p-3 rounded-xl border ${
            failedResults.length > 0
              ? "bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-900/50 text-amber-900 dark:text-amber-200"
              : "bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900/50 text-emerald-900 dark:text-emerald-200"
          }`}
          role="status"
        >
          {describeBatchOutcome(
            outcome.confirmed_count,
            outcome.already_confirmed_count,
            outcome.failed_count
          )}
        </p>

        <ul className="space-y-1.5 mb-4">
          {outcome.results.map((entry, index) => (
            <li
              key={`${entry.scan_id}-${index}`}
              className="flex items-start justify-between gap-2 text-[11px] px-2.5 py-2 rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/60"
            >
              <span className="font-medium text-slate-700 dark:text-slate-300">
                {entry.item_id ?? `Item ${index + 1}`}
              </span>
              <span
                className={
                  entry.status === "failed"
                    ? "text-red-600 dark:text-red-400 text-right"
                    : "text-emerald-700 dark:text-emerald-300 text-right"
                }
              >
                {entry.status === "failed"
                  ? entry.error ?? "Could not be recorded"
                  : entry.status === "already_confirmed"
                  ? `Already recorded (${entry.confirmed_category ?? "unchanged"})`
                  : `Recorded to ${entry.destination ?? "a bin"}`}
              </span>
            </li>
          ))}
        </ul>

        <button
          type="button"
          onClick={onScanAnother}
          className="w-full min-h-[44px] py-3 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold flex items-center justify-center gap-2 active:scale-98 transition-all shadow-md"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Scan Another Scene
        </button>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Review screen
  // -------------------------------------------------------------------------
  return (
    <div className="flex flex-col w-full max-w-md mx-auto gap-3">
      {/* Scene summary */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm p-4">
        <div className="flex items-center gap-2 mb-3">
          <Layers className="w-4 h-4 text-brand-600 dark:text-brand-400" />
          <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
            {result.detection_count} detected item{result.detection_count === 1 ? "" : "s"}
          </h2>
          {reviewCount > 0 && (
            <span className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300">
              <AlertTriangle className="w-3 h-3" />
              {reviewCount} need review
            </span>
          )}
        </div>

        {/* Image with aligned detection boxes */}
        {imageUrl && (
          <div
            className="relative w-full rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800"
            style={{ aspectRatio }}
          >
            <Image
              src={imageUrl}
              alt="Mixed waste scene with detected object boxes"
              fill
              unoptimized
              className="object-contain"
            />
            <DetectionOverlay
              items={result.items}
              selectedItemId={selectedItemId}
              onSelectItem={setSelectedItemId}
              excludedItemIds={excludedItemIds}
              categoryByItemId={categoryByItemId}
            />
          </div>
        )}

        <p className="mt-2 text-[10px] text-slate-400 dark:text-slate-500">
          Boxes show detected objects, not confirmed items. Detected is not the same as confirmed.
        </p>

        <button
          type="button"
          onClick={() => setShowNotes((previous) => !previous)}
          aria-expanded={showNotes}
          className="mt-2 min-h-[44px] w-full flex items-center justify-between gap-2 text-[11px] font-medium text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
        >
          <span className="flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5" />
            Detector: {result.detector_identifier}
          </span>
          <span className="underline">{showNotes ? "Hide limitations" : "Show limitations"}</span>
        </button>

        {showNotes && (
          <div className="mt-1 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/60 space-y-1.5">
            {result.notes.map((note) => (
              <p key={note} className="text-[11px] text-slate-600 dark:text-slate-400 leading-relaxed">
                • {note}
              </p>
            ))}
            <p className="text-[10px] text-slate-500 dark:text-slate-500 font-mono pt-1 border-t border-slate-200 dark:border-slate-700/60">
              Licence: {result.detector_license}
            </p>
          </div>
        )}
      </div>

      {/* Item list */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm p-4 space-y-2.5">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Review detected items
          </h3>
          <span className="text-[10px] text-slate-400">
            {includedItems.length} of {result.items.length} included
          </span>
        </div>

        {result.items.map((item, index) => {
          const itemCategory = categoryByItemId[item.item_id] ?? item.category;
          const style = CATEGORY_STYLES[itemCategory];
          const isSelected = selectedItemId === item.item_id;
          const isExcluded = excludedItemIds.includes(item.item_id);

          return (
            <div
              key={item.item_id}
              className={`rounded-xl border p-3 transition-all ${
                isSelected
                  ? "border-brand-400 dark:border-brand-500 bg-brand-50/50 dark:bg-brand-950/20 ring-1 ring-brand-400"
                  : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/40"
              } ${isExcluded ? "opacity-60" : ""}`}
            >
              <div className="flex items-start justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedItemId(item.item_id)}
                  aria-pressed={isSelected}
                  className="flex-1 text-left min-h-[44px]"
                  aria-label={`Select detection ${index + 1} in the image`}
                >
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-xs font-bold text-slate-900 dark:text-slate-100">
                      {index + 1}. {style.label}
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">
                      score {formatItemScore(item.score)}
                    </span>
                    {item.margin !== null && (
                      <span className="text-[10px] font-mono text-slate-400">
                        margin {item.margin.toFixed(2)}
                      </span>
                    )}
                    {item.review_status === "needs_review" && (
                      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300">
                        <AlertTriangle className="w-2.5 h-2.5" />
                        Review
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5 font-mono">
                    detected as {item.detected_class} · → {item.suggested_destination}
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => toggleExcluded(item.item_id)}
                  aria-label={
                    isExcluded
                      ? `Restore item ${index + 1} to the batch`
                      : `Remove item ${index + 1} from the batch as an incorrect detection`
                  }
                  className={`min-h-[44px] min-w-[44px] rounded-lg flex items-center justify-center border transition-all active:scale-95 ${
                    isExcluded
                      ? "border-slate-300 dark:border-slate-600 text-slate-500"
                      : "border-slate-200 dark:border-slate-700 text-slate-400 hover:text-red-600 hover:border-red-300"
                  }`}
                  title={isExcluded ? "Restore to batch" : "Remove this detection"}
                >
                  {isExcluded ? <Check className="w-4 h-4" /> : <Trash2 className="w-4 h-4" />}
                </button>
              </div>

              {item.review_reasons.length > 0 && (
                <ul className="mt-2 space-y-0.5 pl-0.5">
                  {describeReviewReasons(item.review_reasons).map((reason) => (
                    <li
                      key={reason}
                      className="flex items-start gap-1.5 text-[10px] text-amber-800 dark:text-amber-300"
                    >
                      <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              )}

              {item.cross_check && (
                <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
                  Single-item classifier said{" "}
                  <span className="font-semibold">{item.cross_check.category}</span> (
                  {formatItemScore(item.cross_check.score)}) for this crop.
                </p>
              )}

              <div className="mt-2 grid grid-cols-1 gap-2">
                <label
                  htmlFor={`category-${item.item_id}`}
                  className="text-[10px] font-medium text-slate-500 dark:text-slate-400"
                >
                  Correct the material category if needed:
                </label>
                <select
                  id={`category-${item.item_id}`}
                  value={itemCategory}
                  onChange={(event) =>
                    setCategoryByItemId((previous) => ({
                      ...previous,
                      [item.item_id]: event.target.value as MaterialCategory,
                    }))
                  }
                  disabled={isExcluded}
                  className="w-full min-h-[44px] text-xs px-3 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                  aria-label={`Material category for detection ${index + 1}`}
                >
                  {ALL_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {CATEGORY_STYLES[category].label}
                    </option>
                  ))}
                </select>
              </div>

              <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400 leading-relaxed">
                {item.guidance}
              </p>
            </div>
          );
        })}

        {reviewCount > 0 && (
          <p className="text-[10px] text-amber-700 dark:text-amber-300 leading-relaxed">
            Items marked for review were flagged because of a specific reason listed on each item.
            Nothing is auto-approved on the basis of a high score alone.
          </p>
        )}
      </div>

      {/* Errors */}
      {submitError && (
        <div
          role="alert"
          aria-live="assertive"
          className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 text-red-700 dark:text-red-300 text-xs"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="font-semibold">Batch Confirmation Failed</p>
              <p className="mt-0.5">{submitError}</p>
            </div>
            <button
              type="button"
              onClick={handleRetry}
              className="min-h-[44px] px-2 underline font-medium shrink-0"
              aria-label="Retry batch confirmation"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onScanAnother}
          disabled={isSubmitting}
          className="flex-1 min-h-[44px] py-3 px-4 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs font-semibold flex items-center justify-center gap-1.5 active:scale-98 disabled:opacity-50 transition-all shadow-sm"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Cancel
        </button>

        <button
          type="button"
          onClick={handleConfirm}
          disabled={isSubmitting || includedItems.length === 0}
          className="flex-[2] min-h-[44px] py-3 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold flex items-center justify-center gap-2 active:scale-98 disabled:opacity-50 transition-all shadow-md"
        >
          {isSubmitting ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              Recording {includedItems.length} item
              {includedItems.length === 1 ? "" : "s"}...
            </>
          ) : (
            <>
              <Send className="w-3.5 h-3.5" />
              Confirm {includedItems.length} Item{includedItems.length === 1 ? "" : "s"}
            </>
          )}
        </button>
      </div>

      <p className="text-[10px] text-center text-slate-400 dark:text-slate-500">
        Each item is recorded separately. Inventory changes only for the items you confirm here.
      </p>
    </div>
  );
};
