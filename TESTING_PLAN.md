# Pre-Testing Checklist

What needs to happen before we can do a live end-to-end test of the system.

---

## 1. Missing Secret: `privy_auth.pem`

The backend requires `secrets/privy_auth.pem` (Privy's verification key for JWT validation). All other secrets are present and populated:

| Secret | Status |
|--------|--------|
| `server_secret.txt` | Present |
| `privy_app_id.txt` | Present |
| `privy_app_secret.txt` | Present |
| `privy_auth.pem` | **MISSING** |
| `solana_rpc_url.txt` | Present |
| `arbitrum_rpc_url.txt` | Present |
| `asgard_api_key.txt` | Present |

**Action:** Download the Privy verification key from the Privy dashboard (Settings > Verification Key) and save it to `secrets/privy_auth.pem`.

---

## 2. Fix Failing Frontend Tests (31 failures across 9 files)

All failures are mock setup issues, not real bugs. Three root causes:

### A. OpenPositionModal tests (11 failures)
`useSettingsStore` is not exported from the `../../../stores` mock. The tests need the mock to include it.

**Files:**
- `src/components/positions/__tests__/OpenPositionModal.test.tsx`
- `src/components/positions/__tests__/OpenPositionModal.coverage.test.tsx`
- `src/components/positions/__tests__/modal.submit.test.tsx`

### B. usePositions hook tests (11 failures)
Mock for `positionsApi` doesn't fully cover the async job polling flow. Tests time out waiting for state changes.

**Files:**
- `src/hooks/__tests__/usePositions.errors.test.ts`
- `src/hooks/__tests__/usePositions.polling.test.ts`
- `src/hooks/__tests__/usePositions.coverage.test.ts`

### C. useSettings hook tests (9 failures)
Mock for `settingsApi` missing `loadSettings` / error handling paths. Tests fail on `waitFor` timeouts.

**Files:**
- `src/hooks/__tests__/useSettings.test.ts`
- `src/hooks/__tests__/useSettings.errors.test.ts`
- `src/stores/__tests__/settingsStore.test.ts`

---

## 3. Start Infrastructure (Postgres + Redis)

The backend needs both running. Easiest way:

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis
```

Then verify:
```bash
docker compose -f docker/docker-compose.yml ps
```

Migrations run automatically on backend startup.

---

## 4. Start the Backend

```bash
source .venv/bin/activate
python run_dashboard.py
```

Verify: `curl http://localhost:8000/health` should return `{"status": "ok"}`.

The backend serves the React SPA from `frontend/dist/`, so run `cd frontend && npm run build` first if testing through the backend rather than Vite dev server.

---

## 5. End-to-End Smoke Test

Once infrastructure + backend + frontend are running:

| Step | What to check |
|------|---------------|
| Load `localhost:5173` | Asgard navy theme renders, IBM Plex Sans font |
| Login page | Sunrise gradient background, themed CTA button |
| Click "Get Started" | Privy email modal opens |
| Enter email + OTP | Redirects to dashboard, wallets auto-created |
| Dashboard loads | Rates populate from SSE, leverage slider works |
| Click "Deploy" | Open position modal shows with cost breakdown |
| Cancel modal | Returns to dashboard |
| Check Positions tab | Empty state or existing positions render |
| Check Settings tab | Strategy settings load, presets work |
| Shut Down button | Disabled when no positions open |

---

## 6. Intent UI (Not Yet Built)

The backend has full intent CRUD (`POST/GET/DELETE /api/v1/intents`) but the frontend has no UI for it yet. This means:

- Users can't create limit-style entries ("open when funding > X%")
- Users can't see or cancel pending intents

**Scope:** Add an IntentCard component, a pending intents list on the Dashboard or Positions page, and a cancel button. The API layer already exists.

---

## 7. Python Test Suite

Run with venv activated (system Python lacks asyncpg):

```bash
source .venv/bin/activate
pytest tests/ -v
```

All 1000+ tests should pass. If any fail, it's likely a missing dependency — check `pip install -r requirements/bot.txt`.

---

## Priority Order

1. **`privy_auth.pem`** — blocks backend startup with auth enabled
2. **Start infrastructure** — Postgres + Redis
3. **Start backend + frontend** — smoke test the happy path
4. **Fix frontend test mocks** — cleanup, not blocking functionality
5. **Intent UI** — feature gap, can defer past initial testing
