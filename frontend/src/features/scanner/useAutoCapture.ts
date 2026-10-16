/**
 * ==============================================================================
 * Smart Recycling Agent — Optional Auto-Capture
 * ==============================================================================
 * A conservative, user-controlled automatic shutter for the mixed-scene camera.
 *
 * Design rules this implementation follows deliberately:
 *
 * * It is off until the user turns it on, and it can be stopped at any moment.
 * * It never sends frames to the backend. Nothing is uploaded from the sampling
 *   loop; sampling only decides whether the picture looks still enough. Only the
 *   single captured frame enters the existing scan flow, exactly as if the user
 *   had pressed the shutter.
 * * It never confirms anything and never touches inventory. A capture produces a
 *   preview that still requires an explicit scan and an explicit confirmation.
 * * It waits for a still scene across several samples, then waits out a cooldown,
 *   and it refuses to capture the same scene twice.
 *
 * The stability functions are exported separately from the React hook so the
 * sampling math can be inspected and exercised without a camera attached.
 * ==============================================================================
 */

import { useEffect, useRef, useState } from "react";

/** Downsampled frame grid used as the stability signature. */
export const SIGNATURE_SIZE = 16;
/** Mean luma difference (0-1) below which two frames count as the same view. */
export const STABILITY_DIFFERENCE_THRESHOLD = 0.05;
/** Consecutive still samples required before a capture is allowed. */
export const STABLE_FRAMES_REQUIRED = 3;
/** Wait after a capture before another automatic one may happen. */
export const CAPTURE_COOLDOWN_MS = 4000;
/** A view this similar to the last capture is treated as the same scene. */
export const DUPLICATE_DIFFERENCE_THRESHOLD = 0.02;
export const SAMPLE_INTERVAL_MS = 250;
/** Resolution the video frame is sampled at for stability only. */
export const SAMPLING_CANVAS_SIZE = 64;

export type AutoCaptureStatus = "off" | "waiting" | "steady" | "cooldown";

/**
 * Reduce a frame to a small grid of average luma values.
 *
 * Pixels are sampled with a stride of two so the cost stays bounded regardless of
 * camera resolution. This is a stability signal only: it is never used as image
 * data and never leaves the browser.
 */
export function computeFrameSignature(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  size: number = SIGNATURE_SIZE
): number[] {
  const signature: number[] = [];
  for (let row = 0; row < size; row += 1) {
    const y0 = Math.floor((row * height) / size);
    const y1 = Math.max(y0 + 1, Math.floor(((row + 1) * height) / size));
    for (let col = 0; col < size; col += 1) {
      const x0 = Math.floor((col * width) / size);
      const x1 = Math.max(x0 + 1, Math.floor(((col + 1) * width) / size));
      let sum = 0;
      let count = 0;
      for (let y = y0; y < y1; y += 2) {
        for (let x = x0; x < x1; x += 2) {
          const offset = (y * width + x) * 4;
          // Rec. 601 luma weights.
          sum += 0.299 * pixels[offset] + 0.587 * pixels[offset + 1] + 0.114 * pixels[offset + 2];
          count += 1;
        }
      }
      signature.push(count > 0 ? sum / count : 0);
    }
  }
  return signature;
}

/** Mean absolute luma difference between two signatures, scaled to 0-1. */
export function signatureDifference(a: number[], b: number[]): number {
  if (a.length === 0 || a.length !== b.length) return Number.POSITIVE_INFINITY;
  let total = 0;
  for (let index = 0; index < a.length; index += 1) {
    total += Math.abs(a[index] - b[index]);
  }
  return total / a.length / 255;
}

export interface AutoCaptureOptions {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  /** Only sample while the viewfinder is the screen the user is looking at. */
  active: boolean;
  /** Called with the captured frame. Identical to the manual shutter result. */
  onCapture: (file: File) => void;
  /** Called the moment an automatic capture happens, so it can be announced. */
  onAutoCaptured?: () => void;
}

export interface AutoCaptureController {
  enabled: boolean;
  setEnabled: (next: boolean) => void;
  status: AutoCaptureStatus;
  stableFrames: number;
  /**
   * True only while the sampling loop is actually running. Without this, a
   * caller cannot distinguish "off" from "on but no usable camera", and the
   * status text would claim auto-capture is off while the switch reads enabled.
   */
  samplingActive: boolean;
}

export function useAutoCapture({
  videoRef,
  active,
  onCapture,
  onAutoCaptured,
}: AutoCaptureOptions): AutoCaptureController {
  const [enabled, setEnabled] = useState(false);
  const [status, setStatus] = useState<AutoCaptureStatus>("off");
  const [stableFrames, setStableFrames] = useState(0);

  const previousSignatureRef = useRef<number[] | null>(null);
  const lastCapturedSignatureRef = useRef<number[] | null>(null);
  const lastCaptureAtRef = useRef<number>(0);
  const stableCountRef = useRef(0);

  const onCaptureRef = useRef(onCapture);
  const onAutoCapturedRef = useRef(onAutoCaptured);
  useEffect(() => {
    onCaptureRef.current = onCapture;
    onAutoCapturedRef.current = onAutoCaptured;
  }, [onCapture, onAutoCaptured]);

  // Reset sampling state whenever the mode is switched off or the screen changes.
  useEffect(() => {
    previousSignatureRef.current = null;
    stableCountRef.current = 0;
    setStableFrames(0);
    setStatus(enabled && active ? "waiting" : "off");
  }, [enabled, active]);

  useEffect(() => {
    if (!enabled || !active) return;

    let cancelled = false;
    const canvas = document.createElement("canvas");
    canvas.width = SAMPLING_CANVAS_SIZE;
    canvas.height = SAMPLING_CANVAS_SIZE;
    const context = canvas.getContext("2d", { willReadFrequently: true });

    if (!context) {
      setStatus("off");
      return;
    }

    const sampleFrame = () => {
      if (cancelled) return;
      const video = videoRef.current;
      if (!video || video.readyState < 2 || video.videoWidth === 0) {
        setStatus("waiting");
        return;
      }

      context.drawImage(video, 0, 0, SAMPLING_CANVAS_SIZE, SAMPLING_CANVAS_SIZE);
      const frame = context.getImageData(0, 0, SAMPLING_CANVAS_SIZE, SAMPLING_CANVAS_SIZE);
      const signature = computeFrameSignature(
        frame.data,
        SAMPLING_CANVAS_SIZE,
        SAMPLING_CANVAS_SIZE
      );

      const previous = previousSignatureRef.current;
      previousSignatureRef.current = signature;

      const still =
        previous !== null &&
        signatureDifference(previous, signature) <= STABILITY_DIFFERENCE_THRESHOLD;

      stableCountRef.current = still ? stableCountRef.current + 1 : 0;
      setStableFrames(Math.min(stableCountRef.current, STABLE_FRAMES_REQUIRED));

      if (stableCountRef.current < STABLE_FRAMES_REQUIRED) {
        setStatus("waiting");
        return;
      }
      setStatus("steady");

      const sinceLastCapture = Date.now() - lastCaptureAtRef.current;
      if (sinceLastCapture < CAPTURE_COOLDOWN_MS) {
        setStatus("cooldown");
        return;
      }

      const lastCaptured = lastCapturedSignatureRef.current;
      if (
        lastCaptured !== null &&
        signatureDifference(lastCaptured, signature) <= DUPLICATE_DIFFERENCE_THRESHOLD
      ) {
        // Same scene as the previous capture: do not capture it again.
        setStatus("cooldown");
        return;
      }

      // Capture at full video resolution, exactly like the manual shutter.
      const full = document.createElement("canvas");
      full.width = video.videoWidth;
      full.height = video.videoHeight;
      const fullContext = full.getContext("2d");
      if (!fullContext) {
        setStatus("waiting");
        return;
      }
      fullContext.drawImage(video, 0, 0, full.width, full.height);

      lastCaptureAtRef.current = Date.now();
      lastCapturedSignatureRef.current = signature;
      stableCountRef.current = 0;

      full.toBlob(
        (blob) => {
          if (cancelled || !blob) return;
          onAutoCapturedRef.current?.();
          onCaptureRef.current(
            new File([blob], `auto-scan-${Date.now()}.jpg`, { type: "image/jpeg" })
          );
        },
        "image/jpeg",
        0.92
      );
    };

    const timer = window.setInterval(sampleFrame, SAMPLE_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled, active, videoRef]);

  return { enabled, setEnabled, status, stableFrames, samplingActive: enabled && active };
}
