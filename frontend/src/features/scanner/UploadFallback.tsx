"use client";

import React, { useRef, useState } from "react";
import { Upload, Camera, Image as ImageIcon, AlertCircle } from "lucide-react";

interface UploadFallbackProps {
  onFileSelected: (file: File) => void;
  onSwitchToLiveCamera: () => void;
  canUseLiveCamera: boolean;
}

export const UploadFallback: React.FC<UploadFallbackProps> = ({
  onFileSelected,
  onSwitchToLiveCamera,
  canUseLiveCamera,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const validateAndEmitFile = (file: File) => {
    setUploadError(null);

    // Validate type
    if (!file.type.startsWith("image/")) {
      setUploadError("Please select a valid image file (JPEG, PNG, WEBP).");
      return;
    }

    // Validate size (max 15MB)
    const maxSizeBytes = 15 * 1024 * 1024;
    if (file.size > maxSizeBytes) {
      setUploadError("Image size exceeds 15MB limit. Please choose a smaller photo.");
      return;
    }

    onFileSelected(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      validateAndEmitFile(file);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      validateAndEmitFile(file);
    }
  };

  return (
    <div className="flex flex-col items-center w-full max-w-md mx-auto">
      {/* Hidden file inputs */}
      {/* Standard file picker */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        onChange={handleFileChange}
      />
      {/* Native device camera prompt (works reliably over HTTP LAN on iOS & Android) */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Main Drag-and-Drop Area */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative w-full aspect-[4/5] rounded-2xl border-2 border-dashed transition-all flex flex-col items-center justify-center p-6 text-center cursor-pointer ${
          dragActive
            ? "border-brand-500 bg-brand-50/80 dark:bg-brand-950/40"
            : "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-brand-400"
        } shadow-sm`}
      >
        <div className="w-16 h-16 rounded-full bg-brand-50 dark:bg-brand-950/80 text-brand-600 dark:text-brand-400 flex items-center justify-center mb-4 shadow-inner">
          <Upload className="w-8 h-8" />
        </div>

        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">
          Select or Take Waste Photo
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 max-w-[220px] mb-6">
          Drag and drop an image here, choose from your library, or snap a photo directly.
        </p>

        <div className="flex flex-col sm:flex-row gap-2 w-full max-w-xs">
          {/* Quick Native Camera Button */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              cameraInputRef.current?.click();
            }}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold shadow-sm active:scale-98 transition-all"
          >
            <Camera className="w-4 h-4" />
            Take Photo
          </button>

          {/* Browse Gallery */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold active:scale-98 transition-all"
          >
            <ImageIcon className="w-4 h-4" />
            Browse
          </button>
        </div>
      </div>

      {uploadError && (
        <div className="mt-3 flex items-center gap-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 p-2.5 rounded-xl border border-red-200 dark:border-red-900/50 w-full">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{uploadError}</span>
        </div>
      )}

      {/* Switch to Live Stream Camera when supported */}
      {canUseLiveCamera && (
        <button
          type="button"
          onClick={onSwitchToLiveCamera}
          className="mt-4 flex items-center gap-1.5 text-xs font-medium text-brand-600 dark:text-brand-400 hover:underline"
        >
          <Camera className="w-3.5 h-3.5" />
          Switch to Live Camera Viewfinder
        </button>
      )}
    </div>
  );
};
