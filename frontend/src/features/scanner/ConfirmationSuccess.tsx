"use client";

import React from "react";
import { ScanConfirmationResponse } from "@/types/api";
import { CheckCircle2, ArrowRight } from "lucide-react";

interface ConfirmationSuccessProps {
  confirmation: ScanConfirmationResponse;
  onScanNext: () => void;
}

export const ConfirmationSuccess: React.FC<ConfirmationSuccessProps> = ({
  confirmation,
  onScanNext,
}) => {
  return (
    <div className="flex flex-col items-center w-full max-w-md mx-auto bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-md p-6 text-center animate-in fade-in zoom-in-95 duration-200">
      <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mb-4 shadow-inner">
        <CheckCircle2 className="w-9 h-9" />
      </div>

      <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-1">
        Item Successfully Recorded
      </h2>
      <p className="text-xs text-slate-500 dark:text-slate-400 max-w-xs mb-6">
        The item has been committed to the Digital Twin inventory and material routing flow.
      </p>

      {/* Confirmation Details Card */}
      <div className="w-full bg-slate-50 dark:bg-slate-800/60 rounded-xl p-4 border border-slate-100 dark:border-slate-800 mb-6 text-left space-y-2">
        <div className="flex justify-between items-center text-xs">
          <span className="text-slate-500">Item:</span>
          <span className="font-semibold text-slate-800 dark:text-slate-200">
            {confirmation.confirmed_item}
          </span>
        </div>

        <div className="flex justify-between items-center text-xs">
          <span className="text-slate-500">Category:</span>
          <span className="font-semibold capitalize text-brand-600 dark:text-brand-400">
            {confirmation.confirmed_category}
          </span>
        </div>

        <div className="flex justify-between items-center text-xs">
          <span className="text-slate-500">Destination:</span>
          <span className="font-mono text-slate-700 dark:text-slate-300">
            {confirmation.destination_id}
          </span>
        </div>

        <div className="flex justify-between items-center text-xs border-t border-slate-200 dark:border-slate-700/60 pt-2 text-[11px] text-slate-400">
          <span>Ref ID:</span>
          <span className="font-mono truncate max-w-[160px]">
            {confirmation.confirmation_id}
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={onScanNext}
        className="w-full py-3 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold flex items-center justify-center gap-2 active:scale-98 transition-all shadow-md"
      >
        <span>Scan Next Item</span>
        <ArrowRight className="w-4 h-4" />
      </button>
    </div>
  );
};
