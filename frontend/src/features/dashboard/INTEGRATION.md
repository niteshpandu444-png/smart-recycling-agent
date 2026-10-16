# Digital Twin dashboard integration

The dashboard is available at `/dashboard`. `src/app/dashboard/page.tsx` is its data container; it renders the presentation components in this directory and uses the centralized client in `src/lib/api.ts`.

## Backend data sources

- `GET /api/twin/snapshot` returns `timestamp`, `total_confirmed_items`, `category_inventory`, `bins`, `processing_totals`, and `pending_verification_count`. Bin records provide `accepted_category`, `current_inventory`, `capacity`, `inventory_unit`, `occupancy_percentage`, `status`, and `contamination_risk`.
- `GET /api/events?limit=50` returns `{ items, next_cursor, total_count }`. Event rows provide `id`, `event_type`, `material_id`, `scan_id`, source/destination bin IDs, quantity, unit, `affected_category`, payload, and timestamp.
- `GET /api/recommendations` returns an array of records with `id`, `title`, `recommendation_text`, `generation_method`, `supporting_data`, `status`, and timestamps.
- `POST /api/recommendations/generate` accepts `{ force_refresh?: boolean }` and returns one persisted recommendation record.
- The dashboard maps material-specific bin/event categories into the visual streams `recyclable`, `reusable`, `biodegradable`, `hazardous`, or `unknown`. This is a display grouping; the shared API values remain unchanged. The backend does not supply recommendation severity or action type, so the UI does not invent either field.

`dashboard.adapters.ts` contains the only presentation mapping. The backend response interfaces remain canonical in `src/types/api.ts`; HTTP calls remain centralized in `src/lib/api.ts`.

## Live updates

The page connects to the backend WebSocket at `/ws` using `getWebSocketUrl()` from the shared API client. On connection, the server sends a snapshot envelope. After material event notifications, the dashboard re-queries the snapshot, event history, and recommendations so persisted backend state stays authoritative. A 30-second REST refresh continues while the socket is disconnected, and reconnect attempts use a bounded backoff.

Set `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_WS_URL` in the frontend environment. The WebSocket helper normalizes the configured URL to the documented `/ws` path. Use `wss://` for HTTPS deployments.

Configure the backend's comma-separated `CORS_ORIGINS` value with the exact frontend origin, including its scheme and host and excluding any path. Local development defaults to `http://localhost:3000` and `http://127.0.0.1:3000`; deployment origins must be explicitly configured. The `/ws` handler applies the same allowlist to browser `Origin` headers. Non-browser WebSocket clients without an `Origin` header are permitted.

## Runtime verification note

TypeScript, lint, and production compilation validate the frontend bundle but do not prove that a browser can reach the API. HTTP browser access is controlled by the configurable `CORS_ORIGINS` allowlist. Browser HTTP and WebSocket behavior must still be verified in the target deployment environment.
