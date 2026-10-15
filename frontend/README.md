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
├── API_CONTRACT.md             # Implemented backend API contract
├── package.json
├── tailwind.config.ts
└── tsconfig.json
```

---

## Setup

### 1. Installation
Install project dependencies:
```bash
npm install
```

### 2. Run Development Server
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) on your desktop browser.

### 3. Build & Type Checking
```bash
npm run type-check
npm run lint
npm run build
```

---

## Environment Variables

Copy `.env.example` to create your local environment configuration:
```bash
cp .env.example .env.local
```

Configurable variables:
- `NEXT_PUBLIC_API_BASE_URL`: Base HTTP address for the FastAPI backend (e.g. `http://localhost:8000` or `http://192.168.1.x:8000`).
- `NEXT_PUBLIC_WS_URL`: WebSocket address for live Digital Twin event streaming (e.g. `ws://localhost:8000/ws`).
- `NEXT_PUBLIC_DEV_MODE`: Set to `true` to display developer diagnostics in the UI (such as active idempotency keys). Defaults to `false`.

---

## Phone Testing over HTTPS & Local Network

When testing the mobile scanner on a physical phone:

1. **Local Area Network (LAN) Connectivity:**
   - A mobile phone browsing the application over local Wi-Fi **cannot** use `localhost` to reach the laptop backend (`localhost` on the phone refers to the phone itself).
   - Set `NEXT_PUBLIC_API_BASE_URL=http://<YOUR_LAPTOP_LAN_IP>:8000` in `.env.local` or point to a deployed backend.

2. **HTTPS Requirement for Live Camera Stream:**
   - Modern mobile browsers require a secure context (HTTPS) to grant native live camera stream permissions (`getUserMedia`).
   - To test live camera streaming on a physical phone, access the application through an HTTPS tunnel (e.g., `ngrok`, `local-ssl-proxy`, or `mkcert`) or a deployed HTTPS backend.

3. **Image Upload & Camera Fallback:**
   - When running over unencrypted HTTP LAN without HTTPS, the scanner provides an automatic **Photo Upload / Native Camera** fallback (`<input type="file" capture="environment" />`). This allows capturing photos directly with the phone camera without needing WebRTC HTTPS permissions.

---

## API Contract & Shared Types

Refer to [API_CONTRACT.md](API_CONTRACT.md) for the implemented backend endpoint contracts. Shared TypeScript models are in [src/types/api.ts](src/types/api.ts).

---

## Known Limitations

- **Runtime verification:** The centralized frontend API client completed a scan and confirmation against the running backend using the real ONNX model and an isolated SQLite database. This was not a browser interaction.
- **Camera verification:** Live viewfinder camera streaming (`getUserMedia`) has not been verified in a browser or on a physical phone. The mobile file upload and native camera capture fallback (`capture="environment"`) are available for device testing.
