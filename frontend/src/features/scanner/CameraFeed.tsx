"use client";

import React, { useRef, useState, useEffect, useCallback } from "react";
import {
  Camera,
  RefreshCw,
  AlertCircle,
  Upload,
  SwitchCamera,
  ArrowRight,
} from "lucide-react";
import { submitScan } from "@/lib/api";
import { ScanClassificationResponse } from "@/types/api";

interface CameraFeedProps {
  onCapture: (file: File) => void;
  onLiveConfirm?: (result: ScanClassificationResponse, file: File) => void;
  onError: (errorMsg: string) => void;
  onFallbackToUpload: () => void;
}

export const CameraFeed: React.FC<CameraFeedProps> = ({
  onCapture,
  onLiveConfirm,
  onError,
  onFallbackToUpload,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [facingMode, setFacingMode] = useState<"environment" | "user">("environment");
  const [hasMultipleCameras, setHasMultipleCameras] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [cameraError, setCameraError] = useState<string | null>(null);

  // Live continuous auto-detection state
  const [isAutoDetecting, setIsAutoDetecting] = useState(true);
  const [isAnalyzingLive, setIsAnalyzingLive] = useState(false);
  const [liveResult, setLiveResult] = useState<{
    result: ScanClassificationResponse;
    file: File;
  } | null>(null);
  const isScanningRef = useRef(false);

  // Check if getUserMedia is available in current browser context
  const isGetUserMediaSupported =
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

  // Check if we are in a secure context (required by modern mobile browsers)
  const isSecure = typeof window !== "undefined" ? window.isSecureContext : true;

  const streamRef = useRef<MediaStream | null>(null);

  // Stop active video stream tracks
  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }, []);

  // Check for multiple video input devices
  const checkDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = devices.filter((d) => d.kind === "videoinput");
      setHasMultipleCameras(videoInputs.length > 1);
    } catch {
      // Device enumeration not permitted or supported
    }
  }, []);

  // Initialize camera stream
  const startCamera = useCallback(async () => {
    setIsInitializing(true);
    setCameraError(null);

    if (!isGetUserMediaSupported) {
      const errorMsg =
        "Live camera streaming is not supported by this browser. Please use the photo upload option.";
      setCameraError(errorMsg);
      onError(errorMsg);
      setIsInitializing(false);
      return;
    }

    if (!isSecure && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") {
      const errorMsg =
        "Browsers require HTTPS for live camera access on local network IPs. Please switch to Photo Upload or use HTTPS.";
      setCameraError(errorMsg);
      onError(errorMsg);
      setIsInitializing(false);
      return;
    }

    try {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }

      const newStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: facingMode },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });

      streamRef.current = newStream;
      if (videoRef.current) {
        videoRef.current.srcObject = newStream;
        await videoRef.current.play().catch(() => {});
      }
      checkDevices();
    } catch (err: unknown) {
      let message = "Unable to access camera.";
      if (err instanceof DOMException) {
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
          message = "Camera permission was denied. Please allow camera permissions or use upload.";
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
          message = "No camera hardware detected on this device.";
        } else if (err.name === "NotReadableError" || err.name === "TrackStartError") {
          message = "Camera is currently in use by another application.";
        }
      }
      setCameraError(message);
      onError(message);
    } finally {
      setIsInitializing(false);
    }
  }, [facingMode, isGetUserMediaSupported, isSecure, checkDevices, onError]);

  useEffect(() => {
    startCamera();
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    };
  }, [startCamera]);

  // Continuous real-time frame detection loop
  useEffect(() => {
    if (!isAutoDetecting || isInitializing || Boolean(cameraError)) {
      return;
    }

    const intervalId = setInterval(() => {
      if (isScanningRef.current) return;
      const video = videoRef.current;
      if (!video || video.readyState < 2 || video.paused || video.ended) return;

      const canvas = document.createElement("canvas");
      canvas.width = 320;
      canvas.height = 240;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.drawImage(video, 0, 0, 320, 240);
      canvas.toBlob(
        async (blob) => {
          if (!blob) return;
          const file = new File([blob], `live-scan-${Date.now()}.jpg`, {
            type: "image/jpeg",
          });
          isScanningRef.current = true;
          setIsAnalyzingLive(true);
          try {
            const result = await submitScan(file);
            if (result && (result.predicted_item || result.classification_status === "uncertain")) {
              setLiveResult({ result, file });
            }
          } catch {
            // Silently ignore intermittent background scan errors
          } finally {
            isScanningRef.current = false;
            setIsAnalyzingLive(false);
          }
        },
        "image/jpeg",
        0.82
      );
    }, 1500);

    return () => {
      clearInterval(intervalId);
    };
  }, [isAutoDetecting, isInitializing, cameraError]);

  // Flip between rear and front cameras
  const toggleFacingMode = () => {
    setFacingMode((prev) => (prev === "environment" ? "user" : "environment"));
  };

  // Snapshot frame to File
  const captureFrame = () => {
    if (!videoRef.current) return;
    const video = videoRef.current;

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Draw current video frame to canvas
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      (blob) => {
        if (blob) {
          const file = new File([blob], `scan-${Date.now()}.jpg`, {
            type: "image/jpeg",
          });
          stopStream();
          onCapture(file);
        }
      },
      "image/jpeg",
      0.92
    );
  };

  return (
    <div className="relative flex flex-col items-center w-full max-w-md mx-auto overflow-hidden rounded-2xl bg-black shadow-lg">
      {/* Video Viewport */}
      <div className="relative w-full aspect-[4/5] bg-slate-950 flex items-center justify-center overflow-hidden">
        {isInitializing && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-900/90 text-white">
            <RefreshCw className="w-8 h-8 animate-spin text-brand-400 mb-2" />
            <p className="text-xs font-medium text-slate-300">Initializing camera...</p>
          </div>
        )}

        {cameraError ? (
          <div
            role="alert"
            aria-live="assertive"
            className="p-6 text-center text-slate-200 z-10 flex flex-col items-center max-w-xs"
          >
            <div className="w-12 h-12 rounded-full bg-red-500/20 text-red-400 flex items-center justify-center mb-3">
              <AlertCircle className="w-6 h-6" />
            </div>
            <p className="text-sm font-semibold mb-1">Camera Unavailable</p>
            <p className="text-xs text-slate-400 mb-4">{cameraError}</p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={startCamera}
                className="min-h-[44px] px-4 py-2.5 text-xs font-medium rounded-lg bg-slate-800 text-slate-200 hover:bg-slate-700 active:scale-95 transition-all"
                aria-label="Retry camera initialization"
              >
                Retry
              </button>
              <button
                type="button"
                onClick={onFallbackToUpload}
                className="min-h-[44px] px-4 py-2.5 text-xs font-medium rounded-lg bg-brand-600 text-white hover:bg-brand-500 active:scale-95 transition-all flex items-center gap-1.5"
                aria-label="Switch to photo upload"
              >
                <Upload className="w-3.5 h-3.5" />
                Upload Photo
              </button>
            </div>
          </div>
        ) : (
          <>
            <video
              ref={videoRef}
              playsInline
              muted
              autoPlay
              className="w-full h-full object-cover"
            />

            {/* Live Auto-Scan Status Header */}
            <div className="absolute top-3 left-3 right-3 z-20 flex items-center justify-between pointer-events-auto">
              <button
                type="button"
                onClick={() => setIsAutoDetecting((prev) => !prev)}
                className={`min-h-[44px] px-3 py-1.5 rounded-full backdrop-blur-md border text-xs font-semibold flex items-center gap-2 transition-all shadow-md ${
                  isAutoDetecting
                    ? "bg-slate-900/80 border-emerald-500/50 text-emerald-400"
                    : "bg-slate-900/80 border-slate-700 text-slate-400"
                }`}
                aria-label={isAutoDetecting ? "Pause auto detection" : "Enable auto detection"}
              >
                <span
                  className={`w-2.5 h-2.5 rounded-full ${
                    isAutoDetecting
                      ? isAnalyzingLive
                        ? "bg-brand-400 animate-ping"
                        : "bg-emerald-400 animate-pulse"
                      : "bg-slate-500"
                  }`}
                />
                <span>
                  {isAutoDetecting
                    ? isAnalyzingLive
                      ? "Analyzing Frame..."
                      : "Live Scanner Active"
                    : "Live Scanner Paused"}
                </span>
              </button>
            </div>

            {/* Viewfinder Target Framing Overlay */}
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <div
                className={`relative w-3/4 h-3/4 max-w-[280px] max-h-[280px] rounded-2xl border-2 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)] transition-colors duration-300 ${
                  isAnalyzingLive
                    ? "border-emerald-400 shadow-[0_0_20px_rgba(52,211,153,0.4)]"
                    : "border-brand-400/70"
                }`}
              >
                {/* Target Corners */}
                <div className="absolute -top-1 -left-1 w-5 h-5 border-t-4 border-l-4 border-brand-400 rounded-tl" />
                <div className="absolute -top-1 -right-1 w-5 h-5 border-t-4 border-r-4 border-brand-400 rounded-tr" />
                <div className="absolute -bottom-1 -left-1 w-5 h-5 border-b-4 border-l-4 border-brand-400 rounded-bl" />
                <div className="absolute -bottom-1 -right-1 w-5 h-5 border-b-4 border-r-4 border-brand-400 rounded-br" />

                <div className="absolute -bottom-7 left-0 right-0 text-center">
                  <span className="text-[11px] font-medium tracking-wide uppercase text-white/90 bg-black/60 px-2.5 py-0.5 rounded-full backdrop-blur-sm">
                    Center waste item
                  </span>
                </div>
              </div>
            </div>

            {/* Floating Live Detection HUD */}
            {liveResult && isAutoDetecting && (
              <div
                role="region"
                aria-live="polite"
                className="absolute bottom-3 left-3 right-3 z-20 bg-slate-900/95 backdrop-blur-md border border-brand-500/40 rounded-2xl p-3.5 shadow-2xl animate-in fade-in slide-in-from-bottom-2 duration-200"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
                      <span className="text-[10px] font-bold tracking-wider uppercase text-emerald-400 truncate">
                        Detected Live
                      </span>
                      {liveResult.result.match_score !== null && (
                        <span className="text-[10px] font-mono text-slate-400 shrink-0">
                          ({Math.round(liveResult.result.match_score * 100)}%)
                        </span>
                      )}
                    </div>
                    <h4 className="text-sm font-bold text-white truncate mt-0.5">
                      {liveResult.result.predicted_item || "Uncertain Material"}
                    </h4>
                    <p className="text-[11px] text-slate-300 truncate">
                      {liveResult.result.suggested_route || "Inspect item before sorting"}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      stopStream();
                      if (onLiveConfirm) {
                        onLiveConfirm(liveResult.result, liveResult.file);
                      } else {
                        onCapture(liveResult.file);
                      }
                    }}
                    className="min-h-[44px] px-3.5 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 active:scale-95 text-white text-xs font-bold shadow-lg flex items-center gap-1.5 transition-all shrink-0"
                    aria-label="Confirm detected waste item"
                  >
                    <span>Confirm</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Camera Controls Bar */}
      <div className="w-full bg-slate-900/95 backdrop-blur-sm border-t border-slate-800 p-4 flex items-center justify-between">
        {/* Switch to Upload */}
        <button
          type="button"
          onClick={onFallbackToUpload}
          className="min-h-[44px] min-w-[44px] flex flex-col items-center justify-center rounded-xl text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
          title="Upload from device"
          aria-label="Switch to file upload"
        >
          <Upload className="w-5 h-5" />
          <span className="text-[10px] mt-0.5 font-medium">Upload</span>
        </button>

        {/* Shutter Button */}
        <button
          type="button"
          onClick={captureFrame}
          disabled={Boolean(cameraError) || isInitializing}
          className="relative min-h-[44px] min-w-[44px] flex items-center justify-center w-16 h-16 rounded-full bg-white text-brand-700 shadow-lg active:scale-95 disabled:opacity-40 disabled:pointer-events-none transition-all group"
          aria-label="Capture item photograph"
        >
          <span className="absolute inset-1 rounded-full border-2 border-slate-300 group-hover:border-brand-500 transition-colors" />
          <Camera className="w-7 h-7 text-brand-600" />
        </button>

        {/* Camera Flip (Rear/Front) */}
        <button
          type="button"
          onClick={toggleFacingMode}
          disabled={!hasMultipleCameras && Boolean(cameraError)}
          className="min-h-[44px] min-w-[44px] flex flex-col items-center justify-center rounded-xl text-slate-300 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-30"
          title="Flip camera"
          aria-label="Flip camera direction"
        >
          <SwitchCamera className="w-5 h-5" />
          <span className="text-[10px] mt-0.5 font-medium">Flip</span>
        </button>
      </div>
    </div>
  );
};
