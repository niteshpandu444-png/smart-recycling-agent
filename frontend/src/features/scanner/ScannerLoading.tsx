"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import { Sparkles } from "lucide-react";

interface ScannerLoadingProps {
  imageFile: File;
}

export const ScannerLoading: React.FC<ScannerLoadingProps> = ({ imageFile }) => {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    const objectUrl = URL.createObjectURL(imageFile);
    setPreviewUrl(objectUrl);
    return () => {
      URL.revokeObjectURL(objectUrl);
    };
  }, [imageFile]);

  return (
    <div
      className="flex flex-col items-center w-full max-w-md mx-auto"
      role="status"
      aria-live="polite"
      aria-label="Analyzing image with computer vision"
    >
      {/* Scanning Target with Animated Laser Line */}
      <div className="relative w-full aspect-[4/5] rounded-2xl overflow-hidden bg-slate-950 shadow-lg border-2 border-brand-500/50">
        {previewUrl && (
          <Image
            src={previewUrl}
            alt="Captured waste sample being analyzed"
            fill
            unoptimized
            className="object-cover filter brightness-75 blur-[0.5px]"
          />
        )}

        {/* Ambient Dark Overlay */}
        <div className="absolute inset-0 bg-brand-950/20 mix-blend-multiply" />

        {/* Animated Laser Scan Bar */}
        <div
          className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-brand-400 to-transparent shadow-[0_0_15px_3px_rgba(52,211,153,0.8)] animate-pulse"
          style={{
            animation: "scanLine 2.5s ease-in-out infinite alternate",
          }}
        />

        {/* Framing Grid Overlay */}
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="w-3/4 h-3/4 border border-brand-400/40 rounded-xl relative flex items-center justify-center">
            <div className="w-4 h-4 border-t-2 border-l-2 border-brand-300 absolute -top-1 -left-1" />
            <div className="w-4 h-4 border-t-2 border-r-2 border-brand-300 absolute -top-1 -right-1" />
            <div className="w-4 h-4 border-b-2 border-l-2 border-brand-300 absolute -bottom-1 -left-1" />
            <div className="w-4 h-4 border-b-2 border-r-2 border-brand-300 absolute -bottom-1 -right-1" />

            {/* Center Pulsing Icon */}
            <div className="w-12 h-12 rounded-full bg-brand-500/20 backdrop-blur-md border border-brand-400/40 flex items-center justify-center text-brand-300 animate-pulse">
              <Sparkles className="w-6 h-6" />
            </div>
          </div>
        </div>

        {/* Bottom Banner with Generic Analysis Message */}
        <div className="absolute bottom-3 inset-x-3 bg-black/70 backdrop-blur-md rounded-xl p-3 border border-white/10 text-center">
          <p className="text-xs font-semibold text-brand-300 tracking-wide uppercase">
            Computer Vision Analysis
          </p>
          <p className="text-xs text-white/90 mt-0.5">
            Analyzing image...
          </p>
        </div>
      </div>

      {/* Inline styles for the scan line translation */}
      <style jsx>{`
        @keyframes scanLine {
          0% {
            top: 5%;
          }
          100% {
            top: 92%;
          }
        }
      `}</style>
    </div>
  );
};
