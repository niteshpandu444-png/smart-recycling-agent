"use client";

import React, { useEffect, useState } from "react";
import { Sparkles, RotateCcw, AlertTriangle } from "lucide-react";

interface ImagePreviewProps {
  file: File;
  onRetake: () => void;
  onSubmit: () => void;
  isSubmitting?: boolean;
}

export const ImagePreview: React.FC<ImagePreviewProps> = ({
  file,
  onRetake,
  onSubmit,
  isSubmitting = false,
}) => {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
    return () => {
      URL.revokeObjectURL(objectUrl);
    };
  }, [file]);

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="flex flex-col items-center w-full max-w-md mx-auto">
      {/* Image Preview Box */}
      <div className="relative w-full aspect-[4/5] rounded-2xl overflow-hidden bg-slate-950 shadow-md border border-slate-200 dark:border-slate-800">
        {previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewUrl}
            alt="Captured waste sample"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-slate-400">
            Loading preview...
          </div>
        )}

        {/* Top Floating Badge */}
        <div className="absolute top-3 left-3 bg-black/60 backdrop-blur-md px-3 py-1 rounded-full text-white text-[11px] font-medium flex items-center gap-1.5 border border-white/10">
          <span>{formatFileSize(file.size)}</span>
          <span className="text-white/40">•</span>
          <span className="truncate max-w-[140px]">{file.name}</span>
        </div>
      </div>

      {/* Advisory Note */}
      <div className="mt-3 w-full flex items-start gap-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 p-2.5 rounded-xl text-amber-800 dark:text-amber-300 text-xs">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
        <p>Ensure the item is visible and clearly lit for accurate computer vision classification.</p>
      </div>

      {/* Actions */}
      <div className="mt-4 flex items-center gap-3 w-full">
        <button
          type="button"
          onClick={onRetake}
          disabled={isSubmitting}
          className="flex-1 py-3 px-4 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 text-xs font-semibold flex items-center justify-center gap-2 active:scale-98 disabled:opacity-50 transition-all shadow-sm"
        >
          <RotateCcw className="w-4 h-4" />
          Retake Photo
        </button>

        <button
          type="button"
          onClick={onSubmit}
          disabled={isSubmitting}
          className="flex-1 py-3 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold flex items-center justify-center gap-2 active:scale-98 disabled:opacity-50 transition-all shadow-md"
        >
          <Sparkles className="w-4 h-4" />
          Analyze Waste
        </button>
      </div>
    </div>
  );
};
