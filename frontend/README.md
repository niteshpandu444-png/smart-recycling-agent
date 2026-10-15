# Frontend — Smart Recycling Agent

Code Clash 2.0 — PS 06: Smart Recycling Assistant

Mobile-first web application featuring a computer vision scanner for waste classification and real-time integration with the Digital Twin state engine.

---

## Architecture & Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── globals.css         # Tailwind & mobile safe-area styling
│   │   ├── layout.tsx          # Mobile viewport meta and shell
│   │   └── page.tsx            # Mobile Scanner application page
│   ├── features/
│   │   └── scanner/
│   │       ├── CameraFeed.tsx           # Live camera feed with viewfinder overlay
│   │       ├── UploadFallback.tsx       # Photo upload & native mobile camera trigger
│   │       ├── ImagePreview.tsx         # Snapshot preview with re-take/analyze actions
│   │       ├── ScannerLoading.tsx       # Animated scanning and inference status
│   │       ├── ClassificationCard.tsx   # Results, editable overrides & confirmation
│   │       └── ConfirmationSuccess.tsx  # Verified inventory commit confirmation
│   ├── lib/
│   │   └── api.ts              # Centralized typed HTTP client with error handling
│   └── types/
│       └── api.ts              # Canonical TypeScript interfaces for both scanner & dashboard
├── .env.example                # Environment variables documentation
├── API_CONTRACT.md             # Shared backend & dashboard API contract
├── package.json
├── tailwind.config.ts
└── tsconfig.json
```

---

## Getting Started

### 1. Installation
```bash
npm install
```

### 2. Configure Environment
Copy `.env.example` to `.env.local`:
```bash
cp .env.example .env.local
```

- **Testing locally on laptop:** `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`
- **Testing from mobile device on local Wi-Fi:** Set `NEXT_PUBLIC_API_BASE_URL=http://<YOUR_LAPTOP_IP>:8000`

### 3. Run Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) on your desktop or mobile browser.

### 4. Build & Type Checking
```bash
npm run type-check
npm run build
```

---

## Mobile Camera & Security Guidelines

- Modern browsers require HTTPS or `localhost` to grant live `getUserMedia` camera streams.
- When accessing the application over unencrypted local LAN (`http://192.168.x.x:3000`), modern mobile browsers restrict live camera streams for security.
- The scanner provides an automatic **Photo Upload / Native Camera** fallback (`capture="environment"`), allowing users to snap photos using their mobile phone's native camera even on local HTTP.
- For live viewfinder streaming over Wi-Fi, use an HTTPS reverse tunnel (e.g. `ngrok` or `local-ssl-proxy`).

---

## API Contract & Shared Types

Refer to [API_CONTRACT.md](file:///c:/Users/chint/OneDrive/Desktop/FROUNT%20END/frontend/API_CONTRACT.md) for endpoint contracts, request/response formats, error codes, and WebSocket schemas. Shared TypeScript models are in [src/types/api.ts](file:///c:/Users/chint/OneDrive/Desktop/FROUNT%20END/frontend/src/types/api.ts).
