import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Smart Recycling Agent — Mobile Scanner",
  description:
    "AI-powered mobile recycling assistant combining computer vision, digital twin inventory, and real-time guidance.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
  themeColor: "#059669",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased selection:bg-brand-500 selection:text-white dark:bg-slate-950 dark:text-slate-100">
        <main className="flex min-h-screen flex-col items-center justify-start">
          {children}
        </main>
      </body>
    </html>
  );
}
