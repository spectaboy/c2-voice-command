# Dashboard Implementation Plan

## Scope
`src/dashboard/` only — pure React consumer of WebSocket data from `:8005`.

---

## Phase 1: Scaffold & Foundation

- [x] **1.1** Initialize Vite + React + TypeScript app inside `src/dashboard/`
  - Vite config: dev server on port 3000, proxy WS to `:8005`
  - tsconfig, index.html entry point
- [ ] **1.2** Install dependencies:
  - `react`, `react-dom`, `leaflet`, `react-leaflet`, `@types/leaflet`
  - No UI framework — custom CSS for military dark theme
- [ ] **1.3** Create TypeScript types (`src/dashboard/types.ts`)
  - `WSMessage`, `VehicleStatus`, `IFFAssessment`, `MilitaryCommand`
  - `CommandAck`, `VoiceTranscript`, `ConfirmationRequest`
  - Mirror Python schemas from CLAUDE.md exactly
- [ ] **1.4** Military dark theme CSS (`src/dashboard/styles/theme.css`)
  - Background `#0a0e14`, monospace font
  - Color tokens: friendly `#00ff88`, hostile `#ff3333`, unknown `#ffff00`
  - UPPERCASE headers, subtle scanning line animation on header
  - "UNCLASSIFIED" banner top + bottom

## Phase 2: WebSocket Client & State Management

- [ ] **2.1** WebSocket hook (`src/dashboard/hooks/useWebSocket.ts`)
  - Connect to `ws://localhost:8005/ws`
  - Auto-reconnect with exponential backoff
  - Parse incoming `WSMessage` and dispatch by `type`
- [ ] **2.2** Application state store (`src/dashboard/hooks/useAppState.ts`)
  - `vehicles: Map<string, VehicleStatus>` — keyed by uid
  - `trails: Map<string, Array<[lat, lon]>>` — last 30 positions per vehicle
  - `transcripts: VoiceTranscript[]` — scrolling log
  - `iffAuditLog: IFFAuditEntry[]` — chronological
  - `pendingConfirmation: ConfirmationRequest | null`
  - `commandAcks: Map<string, CommandAck>`
  - Reducers for each WS message type

## Phase 3: Layout & Core Components

- [ ] **3.1** App shell with 4-panel split layout (`src/dashboard/App.tsx`)
  - Top-left 60%: Map panel
  - Top-right 40%: Status cards panel
  - Bottom-left 50%: Voice transcript panel
  - Bottom-right 50%: IFF audit + confirmation panel
  - CSS Grid layout, resizable isn't needed
- [ ] **3.2** Leaflet map component (`src/dashboard/components/TacticalMap.tsx`)
  - CartoDB dark_all basemap
  - Vehicle markers: colored by affiliation, shaped by domain
    - Air: rotated diamond (SVG)
    - Ground: rectangle (SVG)
    - Maritime: lozenge (SVG)
  - Polyline trails (last 30 positions)
  - Click popup: full telemetry detail
  - Center on default position (SITL default area)
- [ ] **3.3** Vehicle status cards (`src/dashboard/components/StatusCards.tsx`)
  - Card per vehicle showing: callsign, mode, battery %, speed, heading, altitude, armed, affiliation
  - Color-coded border by affiliation
  - Pulsing indicator for armed status
- [ ] **3.4** Voice transcript log (`src/dashboard/components/TranscriptLog.tsx`)
  - Scrolling list, newest at bottom, auto-scroll
  - Each entry: timestamp, raw transcript, parsed command summary, confidence bar
  - Color-code by execution status (ack/fail)
- [ ] **3.5** IFF audit trail (`src/dashboard/components/IFFAuditTrail.tsx`)
  - Chronological entries: timestamp, operator, old → new affiliation, threat score, indicators
  - Color-coded rows by new affiliation
- [ ] **3.6** Confirmation modal (`src/dashboard/components/ConfirmationModal.tsx`)
  - Overlay triggered by `confirmation_required` WS message
  - Shows readback text, risk level badge, vehicle callsign
  - CONFIRM / CANCEL buttons
  - On confirm: POST to `/confirm/{command_id}` then dismiss
  - On cancel: POST cancel then dismiss

## Phase 4: Vehicle Markers & Map Symbology

- [ ] **4.1** SVG marker factory (`src/dashboard/components/markers/VehicleMarker.tsx`)
  - Generate Leaflet DivIcon with inline SVG
  - Diamond for air, rectangle for ground, lozenge for maritime
  - Fill color by affiliation (green/red/yellow)
  - Rotate by heading
- [ ] **4.2** Vehicle detail popup component
  - Shown on marker click
  - All telemetry fields formatted with units
  - Close button

## Phase 5: Polish & Demo Readiness

- [ ] **5.1** Scanning line animation on header bar
- [ ] **5.2** Red flash effect on marker when IFF reclassifies to hostile
- [ ] **5.3** Connection status indicator (connected/reconnecting/disconnected)
- [ ] **5.4** Graceful handling of empty state (no vehicles yet)
- [ ] **5.5** Mock data mode for demo without backend (query param `?mock=true`)

## Phase 6: Testing

- [ ] **6.1** Unit tests for type parsing and state reducers
- [ ] **6.2** Component render tests for each panel
- [ ] **6.3** WebSocket mock integration test
- [ ] **6.4** Tests go in `tests/test_dashboard/`

---

## File Structure (Planned)

```
src/dashboard/
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
├── src/
│   ├── main.tsx              # Entry point
│   ├── App.tsx               # 4-panel layout shell
│   ├── types.ts              # All TypeScript interfaces
│   ├── hooks/
│   │   ├── useWebSocket.ts   # WS connection + message dispatch
│   │   └── useAppState.ts    # useReducer-based state management
│   ├── components/
│   │   ├── TacticalMap.tsx       # Leaflet map
│   │   ├── StatusCards.tsx       # Vehicle status cards
│   │   ├── TranscriptLog.tsx     # Voice transcript panel
│   │   ├── IFFAuditTrail.tsx     # IFF audit log
│   │   ├── ConfirmationModal.tsx # Confirmation overlay
│   │   ├── ClassificationBanner.tsx  # UNCLASSIFIED top/bottom
│   │   └── markers/
│   │       └── VehicleMarker.tsx # SVG marker factory
│   └── styles/
│       └── theme.css             # Military dark theme
tests/test_dashboard/
├── types.test.ts
├── useAppState.test.ts
└── components/
    └── ... component tests
```

## Key Design Decisions

1. **No state library** — `useReducer` + context is sufficient for this scale
2. **No UI framework** — custom CSS matches military aesthetic better, fewer deps
3. **SVG markers** — Leaflet DivIcon with inline SVG for full control of shape/color/rotation
4. **Dashboard is read-only** — only WS consumer, except for confirmation POST
5. **Mock mode** — `?mock=true` generates fake vehicle data on interval for standalone demo

## WebSocket Message → State Mapping

| WS `type` | State Update |
|---|---|
| `position_update` | Upsert `vehicles[uid]`, append to `trails[uid]` (cap 30) |
| `iff_change` | Update `vehicles[uid].affiliation`, append to `iffAuditLog` |
| `command_ack` | Upsert `commandAcks[command_id]`, annotate matching transcript |
| `voice_transcript` | Append to `transcripts` |
| `confirmation_required` | Set `pendingConfirmation` |
