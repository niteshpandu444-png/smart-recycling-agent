"use client";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import {
  RecyclingCategory,
  ScanClassificationResponse,
  ScanConfirmationRequest,
} from "@/types/api";
import { generateIdempotencyKey } from "@/lib/api";
import {
  AlertTriangle,
  RotateCcw,
  Send,
  Edit3,
  MapPin,
  RefreshCw,
  Key,
  HelpCircle,
  Undo2,
  Check,
} from "lucide-react";

interface ClassificationCardProps {
  scanResult: ScanClassificationResponse;
  imageFile?: File | null;
  idempotencyKey: string;
  onConfirm: (payload: ScanConfirmationRequest) => Promise<void>;
  onCancel: () => void;
  isConfirming: boolean;
  confirmationError: string | null;
  onRetryConfirmation: () => void;
}

const CATEGORY_STYLES: Record<
  RecyclingCategory,
  { label: string; bg: string; text: string; border: string; description: string }
> = {
  recyclable: {
    label: "Recyclable",
    bg: "bg-emerald-50 dark:bg-emerald-950/40",
    text: "text-emerald-700 dark:text-emerald-300",
    border: "border-emerald-200 dark:border-emerald-800",
    description: "Plastics, paper, cardboard, glass, and clean metals",
  },
  reusable: {
    label: "Reusable",
    bg: "bg-sky-50 dark:bg-sky-950/40",
    text: "text-sky-700 dark:text-sky-300",
    border: "border-sky-200 dark:border-sky-800",
    description: "Functional items, containers, refurbishable electronics",
  },
  biodegradable: {
    label: "Biodegradable",
    bg: "bg-amber-50 dark:bg-amber-950/40",
    text: "text-amber-700 dark:text-amber-300",
    border: "border-amber-200 dark:border-amber-800",
    description: "Compostable organic matter, food scraps, plant fiber",
  },
  hazardous: {
    label: "Hazardous Waste",
    bg: "bg-rose-50 dark:bg-rose-950/40",
    text: "text-rose-700 dark:text-rose-300",
    border: "border-rose-200 dark:border-rose-800",
    description: "Batteries, electronic waste, toxic chemicals, bulbs",
  },
};

const ALL_CATEGORIES: RecyclingCategory[] = [
  "recyclable",
  "reusable",
  "biodegradable",
  "hazardous",
];

export const ClassificationCard: React.FC<ClassificationCardProps> = ({
  scanResult,
  imageFile,
  idempotencyKey,
  onConfirm,
  onCancel,
  isConfirming,
  confirmationError,
  onRetryConfirmation,
}) => {
  // Editable fields for user verification/overrides
  const [isEditing, setIsEditing] = useState(false);
  const [confirmedItem, setConfirmedItem] = useState(scanResult.predicted_item);
  const [confirmedCategory, setConfirmedCategory] = useState<RecyclingCategory>(
    scanResult.predicted_category
  );
  const [destinationId, setDestinationId] = useState(
    scanResult.suggested_route || "bin_general_sorting"
  );
  const [destinationError, setDestinationError] = useState<string | null>(null);

  // Thumbnail rendering & cleanup
  const [imageThumbnailUrl, setImageThumbnailUrl] = useState<string | null>(null);

  // Dynamic idempotency key that rotates whenever payload content changes
  const [activeKey, setActiveKey] = useState<string>(idempotencyKey);
  const [lastSubmittedPayload, setLastSubmittedPayload] =
    useState<ScanConfirmationRequest | null>(null);

  // Revoke object URL cleanly when imageFile changes or unmounts
  useEffect(() => {
    if (!imageFile) {
      setImageThumbnailUrl(null);
      return;
    }
    const url = URL.createObjectURL(imageFile);
    setImageThumbnailUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [imageFile]);

  // Rotate idempotency key when confirmed content changes
  useEffect(() => {
    setActiveKey(generateIdempotencyKey());
  }, [confirmedItem, confirmedCategory, destinationId]);

  const hasModifications =
    confirmedItem !== scanResult.predicted_item ||
    confirmedCategory !== scanResult.predicted_category ||
    destinationId !== (scanResult.suggested_route || "bin_general_sorting");

  const resetToPredicted = () => {
    setConfirmedItem(scanResult.predicted_item);
    setConfirmedCategory(scanResult.predicted_category);
    setDestinationId(scanResult.suggested_route || "bin_general_sorting");
    setDestinationError(null);
  };

  const categoryTheme =
    CATEGORY_STYLES[confirmedCategory] || CATEGORY_STYLES.recyclable;

  const handleConfirmClick = async () => {
    const trimmedItem = confirmedItem.trim() || scanResult.predicted_item;
    const trimmedDestination = destinationId.trim();

    if (!trimmedDestination) {
      setDestinationError("Destination ID cannot be empty. Please specify a target sorting bin.");
      return;
    }
    setDestinationError(null);

    const payload: ScanConfirmationRequest = {
      confirmed_item: trimmedItem,
      confirmed_category: confirmedCategory,
      destination_id: trimmedDestination.slice(0, 64),
      idempotency_key: activeKey,
    };

    setLastSubmittedPayload(payload);
    await onConfirm(payload);
  };

  const handleRetryClick = () => {
    if (lastSubmittedPayload) {
      onConfirm(lastSubmittedPayload);
    } else {
      onRetryConfirmation();
    }
  };

  const matchPercent =
    scanResult.match_score !== undefined && scanResult.match_score !== null
      ? Math.round(scanResult.match_score * 100)
      : null;

  const isDevMode = process.env.NEXT_PUBLIC_DEV_MODE === "true";

  return (
    <div className="flex flex-col w-full max-w-md mx-auto bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-md p-5 animate-in fade-in duration-200">
      {/* Top Bar: Thumbnail Preview + Classification Details */}
      <div className="flex items-start gap-3 border-b border-slate-100 dark:border-slate-800 pb-3 mb-4">
        {imageThumbnailUrl && (
          <div className="relative w-14 h-14 rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 shrink-0 shadow-sm">
            <Image
              src={imageThumbnailUrl}
              alt="Scanned item thumbnail"
              fill
              unoptimized
              className="object-cover"
            />
          </div>
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border ${categoryTheme.bg} ${categoryTheme.text} ${categoryTheme.border}`}
            >
              {categoryTheme.label}
            </span>
            {scanResult.model_identifier && (
              <span className="text-[11px] font-mono text-slate-400 truncate max-w-[140px]">
                {scanResult.model_identifier}
              </span>
            )}
          </div>

          {/* Model Match Score Bar - Neutral color with no implied correctness */}
          {matchPercent !== null && (
            <div className="mt-2.5">
              <div className="flex justify-between items-center text-[10px] text-slate-500 dark:text-slate-400 mb-1">
                <span>Model score (not a probability)</span>
                <span className="font-semibold text-slate-700 dark:text-slate-300">
                  {matchPercent}%
                </span>
              </div>
              <div
                className="w-full h-1.5 bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden"
                role="progressbar"
                aria-valuenow={matchPercent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Model score (not a probability)"
              >
                <div
                  className="h-full rounded-full bg-slate-500 dark:bg-slate-400 transition-all duration-300"
                  style={{ width: `${Math.min(matchPercent, 100)}%` }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Manual Review Alert Banner */}
      {(scanResult.manual_review_recommended ||
        scanResult.classification_status === "uncertain") && (
        <div
          role="alert"
          aria-live="polite"
          className="mb-4 flex items-start gap-2.5 p-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/50 text-amber-900 dark:text-amber-200 text-xs"
        >
          <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
          <div>
            <p className="font-semibold">Manual Verification Recommended</p>
            <p className="mt-0.5 text-amber-800 dark:text-amber-300">
              The model detected ambiguous material features. Please inspect and adjust the item or category if needed before submitting.
            </p>
          </div>
        </div>
      )}

      {/* Item Title & Edit Controls */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <label
            htmlFor="confirmed-item-input"
            className="text-xs font-semibold uppercase tracking-wider text-slate-400"
          >
            Detected Item
          </label>
          <div className="flex items-center gap-2">
            {hasModifications && (
              <button
                type="button"
                onClick={resetToPredicted}
                className="min-h-[44px] px-2 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 flex items-center gap-1 font-medium active:scale-95 transition-all"
                aria-label="Reset fields to model prediction"
                title="Reset to model prediction"
              >
                <Undo2 className="w-3.5 h-3.5" />
                Reset
              </button>
            )}
            <button
              type="button"
              onClick={() => setIsEditing(!isEditing)}
              className="min-h-[44px] px-2 text-xs text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1 font-medium active:scale-95 transition-all"
              aria-label={isEditing ? "Finish editing fields" : "Edit item details and category"}
            >
              <Edit3 className="w-3.5 h-3.5" />
              {isEditing ? "Done Editing" : "Edit Fields"}
            </button>
          </div>
        </div>

        {isEditing ? (
          <div className="space-y-3 p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-slate-200 dark:border-slate-700/60">
            <div>
              <label
                htmlFor="confirmed-item-input"
                className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1 block"
              >
                Item Description:
              </label>
              <input
                id="confirmed-item-input"
                type="text"
                maxLength={128}
                value={confirmedItem}
                onChange={(e) => setConfirmedItem(e.target.value)}
                className="w-full min-h-[44px] text-sm font-medium px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="Enter item description"
                aria-label="Item description input"
              />
            </div>

            <div>
              <label className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1 block">
                Material Category:
              </label>
              <div className="grid grid-cols-2 gap-2" role="group" aria-label="Select material category">
                {ALL_CATEGORIES.map((cat) => {
                  const style = CATEGORY_STYLES[cat];
                  const isSelected = confirmedCategory === cat;
                  return (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => setConfirmedCategory(cat)}
                      aria-label={`Select category: ${style.label}`}
                      aria-pressed={isSelected}
                      className={`min-h-[44px] p-2.5 rounded-lg text-xs font-medium border text-left transition-all ${
                        isSelected
                          ? `${style.bg} ${style.text} ${style.border} ring-2 ring-brand-500 shadow-sm`
                          : "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span>{style.label}</span>
                        {isSelected && <Check className="w-3.5 h-3.5" />}
                      </div>
                      <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5 line-clamp-1">
                        {style.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label
                htmlFor="destination-input"
                className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1 block"
              >
                Destination Route / Bin ID (Max 64 chars):
              </label>
              <input
                id="destination-input"
                type="text"
                maxLength={64}
                value={destinationId}
                onChange={(e) => {
                  setDestinationId(e.target.value);
                  if (destinationError) setDestinationError(null);
                }}
                className={`w-full min-h-[44px] text-xs font-mono px-3 py-2 rounded-lg border bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                  destinationError
                    ? "border-red-500 focus:ring-red-500"
                    : "border-slate-300 dark:border-slate-600"
                }`}
                placeholder="Destination Bin ID (Required)"
                aria-label="Destination Route or Bin ID input"
              />
              {destinationError && (
                <p role="alert" aria-live="assertive" className="text-xs text-red-600 dark:text-red-400 mt-1">
                  {destinationError}
                </p>
              )}
            </div>
          </div>
        ) : (
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              {confirmedItem}
            </h2>
            {hasModifications && (
              <span className="inline-block mt-0.5 text-[10px] font-semibold text-brand-600 dark:text-brand-400">
                (Modified by user)
              </span>
            )}
          </div>
        )}
      </div>

      {/* Route & Guidance */}
      <div className="mb-4 bg-slate-50 dark:bg-slate-800/60 rounded-xl p-3.5 border border-slate-100 dark:border-slate-800 space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-800 dark:text-slate-200">
          <MapPin className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400 shrink-0" />
          <span>Routing:</span>
          <span className="text-brand-700 dark:text-brand-300 font-mono">
            {destinationId || "Unassigned"}
          </span>
        </div>

        {scanResult.explanation && (
          <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            {scanResult.explanation}
          </p>
        )}
      </div>

      {/* Idempotency Key Status Pill - Hidden unless NEXT_PUBLIC_DEV_MODE=true */}
      {isDevMode && (
        <div className="mb-4 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400 bg-slate-100/70 dark:bg-slate-800/50 px-2.5 py-1.5 rounded-lg">
          <div className="flex items-center gap-1.5 font-mono">
            <Key className="w-3 h-3 text-slate-400 shrink-0" />
            <span className="truncate max-w-[200px]" title={activeKey}>
              Key: {activeKey}
            </span>
          </div>
          <span
            className="text-[10px] text-slate-400 flex items-center gap-0.5 cursor-help"
            title="Stable key prevents duplicate records if confirmation is retried"
          >
            <HelpCircle className="w-3 h-3" />
            Idempotent (Dev Mode)
          </span>
        </div>
      )}

      {/* Confirmation Error Notification with Retry */}
      {confirmationError && (
        <div
          role="alert"
          aria-live="assertive"
          className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 text-red-700 dark:text-red-300 text-xs"
        >
          <div className="flex items-start justify-between">
            <p className="font-semibold">Confirmation Failed</p>
            <button
              type="button"
              onClick={handleRetryClick}
              className="min-h-[44px] px-2 text-red-800 dark:text-red-200 underline font-medium hover:text-red-900 ml-2"
              aria-label="Retry confirmation request"
            >
              Retry Submission
            </button>
          </div>
          <p className="mt-1">{confirmationError}</p>
        </div>
      )}

      {/* Action Controls with minimum 44px tap targets */}
      <div className="flex items-center gap-3 pt-1">
        <button
          type="button"
          onClick={onCancel}
          disabled={isConfirming}
          className="flex-1 min-h-[44px] py-3 px-4 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold flex items-center justify-center gap-1.5 active:scale-98 disabled:opacity-50 transition-all shadow-sm"
          aria-label="Cancel and rescan item"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Cancel / Rescan
        </button>

        <button
          type="button"
          onClick={handleConfirmClick}
          disabled={isConfirming}
          className="flex-[2] min-h-[44px] py-3 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold flex items-center justify-center gap-2 active:scale-98 disabled:opacity-50 transition-all shadow-md"
          aria-label="Confirm item and commit to Digital Twin"
        >
          {isConfirming ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              Recording in Twin...
            </>
          ) : (
            <>
              <Send className="w-3.5 h-3.5" />
              Confirm & Commit Item
            </>
          )}
        </button>
      </div>

      <div className="mt-2.5 text-center">
        <span className="text-[10px] text-slate-400">
          Digital Twin inventory increments only upon verified backend confirmation.
        </span>
      </div>
    </div>
  );
};
