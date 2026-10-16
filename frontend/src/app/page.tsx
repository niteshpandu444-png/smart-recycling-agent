"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { CameraFeed } from "@/features/scanner/CameraFeed";
import { UploadFallback } from "@/features/scanner/UploadFallback";
import { ImagePreview } from "@/features/scanner/ImagePreview";
import { ScannerLoading } from "@/features/scanner/ScannerLoading";
import { ClassificationCard } from "@/features/scanner/ClassificationCard";
import { ConfirmationSuccess } from "@/features/scanner/ConfirmationSuccess";
import { BatchScanView } from "@/features/scanner/BatchScanView";
import {
  submitScan,
  submitBatchScan,
  confirmScan,
  confirmBatch,
  getHealth,
  generateIdempotencyKey,
  getApiBaseUrl,
  ApiError,
} from "@/lib/api";
import {
  BatchScanResponse,
  ScanClassificationResponse,
  ScanConfirmationRequest,
  ScanConfirmationResponse,
} from "@/types/api";
import {
  Leaf,
  Wifi,
  WifiOff,
  AlertCircle,
  RefreshCw,
  Camera,
  Upload,
  Layers,
  Package,
} from "lucide-react";

type ScannerState =
  | "CAMERA"
  | "UPLOAD"
  | "PREVIEW"
  | "ANALYZING"
  | "CLASSIFIED"
  | "CONFIRMED"
  | "MIXED_REVIEW";

/** How many waste items the user is pointing the camera at. */
type ScanMode = "single" | "mixed";

/** Which input produced the current image, recorded as batch provenance. */
type CaptureSource = "camera" | "upload";

export default function MobileScannerPage() {
  const [currentState, setCurrentState] = useState<ScannerState>("CAMERA");
  const [scanMode, setScanMode] = useState<ScanMode>("single");
  const [capturedFile, setCapturedFile] = useState<File | null>(null);
  const [captureSource, setCaptureSource] = useState<CaptureSource>("camera");

  // Classification State
  const [classificationResult, setClassificationResult] =
    useState<ScanClassificationResponse | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);

  // Mixed-scene batch state
  const [batchResult, setBatchResult] = useState<BatchScanResponse | null>(null);

  // Confirmation State
  const [isConfirming, setIsConfirming] = useState(false);
  const [confirmationError, setConfirmationError] = useState<string | null>(null);
  const [confirmationResult, setConfirmationResult] =
    useState<ScanConfirmationResponse | null>(null);
  const [activeIdempotencyKey, setActiveIdempotencyKey] = useState<string>("");
  const [lastConfirmationPayload, setLastConfirmationPayload] =
    useState<ScanConfirmationRequest | null>(null);

  // Backend Health State
  const [backendStatus, setBackendStatus] = useState<"checking" | "online" | "offline">("checking");

  // Check backend health on mount
  const checkHealth = useCallback(async () => {
    setBackendStatus("checking");
    try {
      await getHealth();
      setBackendStatus("online");
    } catch {
      setBackendStatus("offline");
    }
  }, []);

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  // Handle capture from live camera or file picker
  const handleImageCaptured = (file: File, source: CaptureSource = "upload") => {
    setCapturedFile(file);
    setCaptureSource(source);
    setScanError(null);
    setCurrentState("PREVIEW");
  };

  // Submit image to backend API. A mixed scene goes to the detector pipeline and a
  // single item keeps using the existing whole-image classification endpoint.
  // Handle instant live detection from continuous camera stream
  const handleLiveDetected = async (file: File) => {
    setCapturedFile(file);
    setCaptureSource("camera");
    setScanError(null);
    setCurrentState("ANALYZING");
    try {
      // Persist only the frame the user selected. Inventory still requires the
      // separate explicit confirmation action in ClassificationCard.
      const result = await submitScan(file);
      setClassificationResult(result);
      setActiveIdempotencyKey(generateIdempotencyKey());
      setCurrentState("CLASSIFIED");
    } catch (err: unknown) {
      setScanError(err instanceof ApiError ? err.message : "Failed to classify the selected frame.");
      setCurrentState("PREVIEW");
    }
  };

  // Submit image to backend API
  const handleAnalyzeImage = async () => {
    if (!capturedFile) return;

    setCurrentState("ANALYZING");
    setScanError(null);

    try {
      if (scanMode === "mixed") {
        const result = await submitBatchScan(capturedFile, captureSource);
        setBatchResult(result);
        setCurrentState("MIXED_REVIEW");
        return;
      }

      const result = await submitScan(capturedFile);
      setClassificationResult(result);
      // Reset idempotency key for this new scan
      setActiveIdempotencyKey(generateIdempotencyKey());
      setCurrentState("CLASSIFIED");
    } catch (err: unknown) {
      const errorMessage =
        err instanceof ApiError
          ? err.message
          : scanMode === "mixed"
          ? "Failed to analyze the scene. Please ensure the backend server is reachable."
          : "Failed to classify image. Please ensure the backend server is reachable.";
      setScanError(errorMessage);
      setCurrentState("PREVIEW");
    }
  };

  // Confirm and commit a single item to the Digital Twin
  const handleConfirmClassification = async (payload: ScanConfirmationRequest) => {
    if (!classificationResult) return;

    setIsConfirming(true);
    setConfirmationError(null);

    // Reuse or create stable idempotency key
    const idempKey = activeIdempotencyKey || generateIdempotencyKey();
    if (!activeIdempotencyKey) {
      setActiveIdempotencyKey(idempKey);
    }

    const fullPayload: ScanConfirmationRequest = {
      ...payload,
      idempotency_key: payload.idempotency_key || idempKey,
    };
    setLastConfirmationPayload(fullPayload);

    try {
      const res = await confirmScan(classificationResult.scan_id, fullPayload);
      setConfirmationResult(res);
      setCurrentState("CONFIRMED");
    } catch (err: unknown) {
      const errorMsg =
        err instanceof ApiError
          ? err.message
          : "Failed to record item in the Digital Twin. You can retry with the same key.";
      setConfirmationError(errorMsg);
    } finally {
      setIsConfirming(false);
    }
  };

  // Retry confirmation
  const handleRetryConfirmation = async () => {
    if (lastConfirmationPayload) {
      await handleConfirmClassification(lastConfirmationPayload);
    }
  };

  // Reset to scan new item
  const handleResetToScanner = () => {
    setCapturedFile(null);
    setClassificationResult(null);
    setBatchResult(null);
    setConfirmationResult(null);
    setScanError(null);
    setConfirmationError(null);
    setActiveIdempotencyKey("");
    setLastConfirmationPayload(null);
    setCurrentState("CAMERA");
  };

  const handleModeChange = (mode: ScanMode) => {
    if (mode === scanMode) return;
    setScanMode(mode);
    setScanError(null);
    setCurrentState("CAMERA");
  };

  const isMixedMode = scanMode === "mixed";

  return (
    <div className="w-full min-h-screen flex flex-col items-center justify-start bg-slate-50 dark:bg-slate-950 px-4 py-4 sm:py-8 safe-top safe-bottom">
      {/* App Header & Service Status Indicator */}
      <header className="w-full max-w-md flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm">
            <Leaf className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-slate-900 dark:text-white leading-none">
              Smart Recycling
            </h1>
            <p className="text-[10px] text-slate-500 dark:text-slate-400 font-medium mt-0.5">
              Mobile Assistant • PS 06
            </p>
          </div>
        </div>

        <Link href="/dashboard" className="text-xs font-semibold text-brand-700 hover:text-brand-600 dark:text-brand-300">
          Digital Twin
        </Link>

        {/* Backend Connectivity Status Pill */}
        <button
          type="button"
          onClick={checkHealth}
          className={`min-h-[44px] flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-medium border transition-colors ${
            backendStatus === "online"
              ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
              : backendStatus === "checking"
              ? "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400"
              : "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800"
          }`}
          title={`Backend: ${getApiBaseUrl()}`}
          aria-label="Check backend connection status"
        >
          {backendStatus === "online" && (
            <>
              <Wifi className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>Backend Ready</span>
            </>
          )}
          {backendStatus === "checking" && (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-400" />
              <span>Connecting...</span>
            </>
          )}
          {backendStatus === "offline" && (
            <>
              <WifiOff className="w-3.5 h-3.5 text-rose-500" />
              <span>Backend Offline</span>
            </>
          )}
        </button>
      </header>

      {/* Scanning Mode Switcher (Single Item vs Mixed Scene) when idle */}
      {(currentState === "CAMERA" || currentState === "UPLOAD") && (
        <div className="w-full max-w-md flex bg-slate-200/70 dark:bg-slate-800 p-1 rounded-xl mb-2 text-xs font-semibold">
          <button
            type="button"
            onClick={() => handleModeChange("single")}
            aria-pressed={!isMixedMode}
            className={`flex-1 min-h-[44px] py-2 rounded-lg flex items-center justify-center gap-1.5 transition-all ${
              !isMixedMode
                ? "bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 shadow-sm"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
            }`}
            aria-label="Scan one waste item at a time"
          >
            <Package className="w-4 h-4" />
            Single Item
          </button>
          <button
            type="button"
            onClick={() => handleModeChange("mixed")}
            aria-pressed={isMixedMode}
            className={`flex-1 min-h-[44px] py-2 rounded-lg flex items-center justify-center gap-1.5 transition-all ${
              isMixedMode
                ? "bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 shadow-sm"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
            }`}
            aria-label="Scan a mixed scene containing several waste items"
          >
            <Layers className="w-4 h-4" />
            Mixed Scene
          </button>
        </div>
      )}

      {/* Mode Explanation Banner */}
      {(currentState === "CAMERA" || currentState === "UPLOAD") && isMixedMode && (
        <p className="w-full max-w-md mb-3 text-[10px] text-slate-500 dark:text-slate-400 leading-relaxed">
          Detects each waste item separately and marks uncertain detections for review. Detected
          items are not inventory until you confirm them.
        </p>
      )}

      {/* Mode Switcher (Camera vs Upload) when idle */}
      {(currentState === "CAMERA" || currentState === "UPLOAD") && (
        <div className="w-full max-w-md flex bg-slate-200/70 dark:bg-slate-800 p-1 rounded-xl mb-4 text-xs font-semibold">
          <button
            type="button"
            onClick={() => setCurrentState("CAMERA")}
            className={`flex-1 min-h-[44px] py-2 rounded-lg flex items-center justify-center gap-1.5 transition-all ${
              currentState === "CAMERA"
                ? "bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 shadow-sm"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
            }`}
            aria-label="Switch to live camera viewfinder"
          >
            <Camera className="w-4 h-4" />
            Live Viewfinder
          </button>
          <button
            type="button"
            onClick={() => setCurrentState("UPLOAD")}
            className={`flex-1 min-h-[44px] py-2 rounded-lg flex items-center justify-center gap-1.5 transition-all ${
              currentState === "UPLOAD"
                ? "bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 shadow-sm"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
            }`}
            aria-label="Switch to photo upload"
          >
            <Upload className="w-4 h-4" />
            Photo Upload
          </button>
        </div>
      )}

      {/* Global Error Banner for states other than preview */}
      {scanError && currentState !== "PREVIEW" && (
        <div
          role="alert"
          aria-live="assertive"
          className="w-full max-w-md mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 text-red-700 dark:text-red-300 text-xs flex items-start gap-2.5"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-red-600 dark:text-red-400" />
          <div className="flex-1">
            <p className="font-semibold">
              {isMixedMode ? "Scene Analysis Error" : "Classification Error"}
            </p>
            <p className="mt-0.5 text-red-600 dark:text-red-300">{scanError}</p>
          </div>
        </div>
      )}

      {/* State 1 & 2: Live Camera Viewfinder */}
      {currentState === "CAMERA" && (
        <CameraFeed
          onCapture={handleImageCaptured}
          onLiveConfirm={handleLiveDetected}
          onError={(msg) => console.warn(msg)}
          onFallbackToUpload={() => setCurrentState("UPLOAD")}
          autoCaptureAvailable={isMixedMode}
        />
      )}

      {/* State 3: Upload Fallback */}
      {currentState === "UPLOAD" && (
        <UploadFallback
          onFileSelected={(file) => handleImageCaptured(file, "upload")}
          onSwitchToLiveCamera={() => setCurrentState("CAMERA")}
          canUseLiveCamera={true}
        />
      )}

      {/* State 4: Captured Image Preview */}
      {currentState === "PREVIEW" && capturedFile && (
        <ImagePreview
          file={capturedFile}
          onRetake={handleResetToScanner}
          onSubmit={handleAnalyzeImage}
          errorMessage={scanError}
          submitLabel={isMixedMode ? "Detect Items" : "Analyze Waste"}
          hintText={
            isMixedMode
              ? "Lay the items out so they are visible and not heavily overlapping, then detect each one."
              : "Ensure the item is visible and clearly lit for accurate computer vision classification."
          }
        />
      )}

      {/* State 5: Loading State during inference */}
      {currentState === "ANALYZING" && capturedFile && (
        <ScannerLoading imageFile={capturedFile} />
      )}

      {/* State 6 - 11: Classification Results & Review Card */}
      {currentState === "CLASSIFIED" && classificationResult && (
        <ClassificationCard
          scanResult={classificationResult}
          imageFile={capturedFile}
          idempotencyKey={activeIdempotencyKey}
          onConfirm={handleConfirmClassification}
          onCancel={handleResetToScanner}
          isConfirming={isConfirming}
          confirmationError={confirmationError}
          onRetryConfirmation={handleRetryConfirmation}
        />
      )}

      {/* Mixed-scene batch review screen */}
      {currentState === "MIXED_REVIEW" && batchResult && capturedFile && (
        <BatchScanView
          imageFile={capturedFile}
          result={batchResult}
          onSubmit={confirmBatch}
          onScanAnother={handleResetToScanner}
        />
      )}

      {/* State 12: Confirmation Success */}
      {currentState === "CONFIRMED" && confirmationResult && (
        <ConfirmationSuccess
          confirmation={confirmationResult}
          onScanNext={handleResetToScanner}
        />
      )}

      {/* Footer System Info */}
      <footer className="mt-6 w-full max-w-md text-center text-[10px] text-slate-400 dark:text-slate-500">
        <p>Connected to Backend: {getApiBaseUrl()}</p>
        <p className="mt-0.5">Code Clash 2.0 • Digital Twin Synchronization Protocol</p>
      </footer>
    </div>
  );
}
