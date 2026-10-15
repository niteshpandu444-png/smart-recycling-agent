"use client";

import React, { useState } from "react";
import {
  RecyclingCategory,
  ScanClassificationResponse,
  ScanConfirmationRequest,
} from "@/types/api";
import {
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Send,
  Edit2,
  Info,
  MapPin,
  RefreshCw,
} from "lucide-react";

interface ClassificationCardProps {
  scanResult: ScanClassificationResponse;
  onConfirm: (payload: ScanConfirmationRequest) => Promise<void>;
  onCancel: () => void;
  isConfirming: boolean;
  confirmationError: string | null;
  onRetryConfirmation: () => void;
}

const CATEGORY_STYLES: Record<
  RecyclingCategory,
  { label: string; bg: string; text: string; border: string }
> = {
  recyclable: {
    label: "Recyclable",
    bg: "bg-emerald-50 dark:bg-emerald-950/40",
    text: "text-emerald-700 dark:text-emerald-300",
    border: "border-emerald-200 dark:border-emerald-800",
  },
  reusable: {
    label: "Reusable",
    bg: "bg-sky-50 dark:bg-sky-950/40",
    text: "text-sky-700 dark:text-sky-300",
    border: "border-sky-200 dark:border-sky-800",
  },
  biodegradable: {
    label: "Biodegradable",
    bg: "bg-amber-50 dark:bg-amber-950/40",
    text: "text-amber-700 dark:text-amber-300",
    border: "border-amber-200 dark:border-amber-800",
  },
  hazardous: {
    label: "Hazardous Waste",
    bg: "bg-rose-50 dark:bg-rose-950/40",
    text: "text-rose-700 dark:text-rose-300",
    border: "border-rose-200 dark:border-rose-800",
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
  // Default destination from prediction
  const [destinationId] = useState(
    scanResult.suggested_route || "bin_general_sort"
  );

  const categoryTheme =
    CATEGORY_STYLES[confirmedCategory] || CATEGORY_STYLES.recyclable;

  const handleConfirmClick = async () => {
    // Generate or reuse stable idempotency key in parent
    await onConfirm({
      confirmed_item: confirmedItem.trim() || scanResult.predicted_item,
      confirmed_category: confirmedCategory,
      destination_id: destinationId,
      idempotency_key: "", // Populated stably in page state
    });
  };

  return (
    <div className="flex flex-col w-full max-w-md mx-auto bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-md p-5">
      {/* Header with Status and Match Score */}
      <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3 mb-4">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border ${categoryTheme.bg} ${categoryTheme.text} ${categoryTheme.border}`}
          >
            {categoryTheme.label}
          </span>
          <span className="text-[11px] text-slate-400 font-mono">
            {scanResult.model_identifier}
          </span>
        </div>

        {scanResult.match_score !== undefined && scanResult.match_score !== null && (
          <div
            className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400"
            title="Model-specific confidence score (not guaranteed probability)"
          >
            <span className="font-semibold text-slate-800 dark:text-slate-200">
              {Math.round(scanResult.match_score * 100)}%
            </span>
            <span className="text-[10px]">match score</span>
          </div>
        )}
      </div>

      {/* Manual Review Alert Banner */}
      {(scanResult.manual_review_recommended ||
        scanResult.classification_status === "uncertain") && (
        <div className="mb-4 flex items-start gap-2.5 p-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/50 text-amber-900 dark:text-amber-200 text-xs">
          <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
          <div>
            <p className="font-semibold">Manual Verification Recommended</p>
            <p className="mt-0.5 text-amber-800 dark:text-amber-300">
              The model detected ambiguous material features. Please confirm or edit the classification below before submitting.
            </p>
          </div>
        </div>
      )}

      {/* Item Title & Edit Controls */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Detected Item
          </label>
          <button
            type="button"
            onClick={() => setIsEditing(!isEditing)}
            className="text-xs text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1 font-medium"
          >
            <Edit2 className="w-3 h-3" />
            {isEditing ? "Done" : "Edit Item"}
          </button>
        </div>

        {isEditing ? (
          <div className="space-y-3">
            <input
              type="text"
              value={confirmedItem}
              onChange={(e) => setConfirmedItem(e.target.value)}
              className="w-full text-sm font-medium px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
              placeholder="Enter item description"
            />

            <div>
              <label className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-1 block">
                Override Material Category:
              </label>
              <div className="grid grid-cols-2 gap-1.5">
                {ALL_CATEGORIES.map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setConfirmedCategory(cat)}
                    className={`py-1.5 px-2 rounded-lg text-xs font-medium border text-left capitalize transition-colors ${
                      confirmedCategory === cat
                        ? `${CATEGORY_STYLES[cat].bg} ${CATEGORY_STYLES[cat].text} ${CATEGORY_STYLES[cat].border} ring-1 ring-brand-500`
                        : "border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 text-slate-600 dark:text-slate-400"
                    }`}
                  >
                    {CATEGORY_STYLES[cat].label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {confirmedItem}
          </h2>
        )}
      </div>

      {/* Route & Guidance */}
      <div className="mb-4 bg-slate-50 dark:bg-slate-800/60 rounded-xl p-3.5 border border-slate-100 dark:border-slate-800 space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-800 dark:text-slate-200">
          <MapPin className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400 shrink-0" />
          <span>Proposed Route:</span>
          <span className="text-brand-700 dark:text-brand-300 font-mono">
            {scanResult.suggested_route || "Default Sorting Bin"}
          </span>
        </div>

        {scanResult.explanation && (
          <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            {scanResult.explanation}
          </p>
        )}
      </div>

      {/* Confirmation Error Notification with Retry */}
      {confirmationError && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 text-red-700 dark:text-red-300 text-xs">
          <div className="flex items-start justify-between">
            <p className="font-semibold">Confirmation Failed</p>
            <button
              onClick={onRetryConfirmation}
              className="text-red-800 dark:text-red-200 underline font-medium hover:text-red-900 ml-2"
            >
              Retry
            </button>
          </div>
          <p className="mt-1">{confirmationError}</p>
        </div>
      )}

      {/* Action Controls */}
      <div className="flex items-center gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={isConfirming}
          className="flex-1 py-3 px-4 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold flex items-center justify-center gap-1.5 active:scale-98 disabled:opacity-50 transition-all shadow-sm"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Rescan
        </button>

        <button
          type="button"
          onClick={handleConfirmClick}
          disabled={isConfirming}
          className="flex-[2] py-3 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold flex items-center justify-center gap-2 active:scale-98 disabled:opacity-50 transition-all shadow-md"
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
          Item is committed to inventory only after backend confirmation.
        </span>
      </div>
    </div>
  );
};
