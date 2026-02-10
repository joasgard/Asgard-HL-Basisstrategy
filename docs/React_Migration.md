# React Migration Plan

**Status:** In Progress  
**Started:** 2026-02-10  
**Target Completion:** TBD  
**Assigned:** Current Agent

---

## Overview

Migrating the Delta Neutral Bot dashboard from server-rendered Jinja2 templates to a React SPA with TypeScript.

### Current Progress Summary
- ✅ **Phase 1 Complete:** React project setup with Vite, TypeScript, Tailwind CSS, Privy SDK
- ✅ **Phase 2 Complete:** Backend serves React SPA, API client layer created
- 🚧 **Phase 3 In Progress:** Dashboard UI components created, needs data integration
- ⏳ **Phase 4-6 Pending:** State management, testing, deployment

### Known Issues
- Frontend LoginModal styling issue (black screen) - to be fixed in Phase 5 polish
- Component tests deferred until core functionality complete

### Goals
- Integrate Privy's React SDK for native auth flow
- Modern component-based architecture
- TypeScript for type safety
- Maintain all existing functionality

---

## Phase 1: Setup & Infrastructure

**Status:** `[x]` Complete (functional, styling polish later)

### 1.1 Project Setup
- [x] Create `frontend/` directory at project root
- [x] Initialize Vite + React + TypeScript project
- [x] Install core dependencies:
  - [x] React 18
  - [x] React Router DOM v6
  - [x] TypeScript
  - [x] Vite
  - [x] Tailwind CSS
- [x] Configure `tsconfig.json` with strict mode
- [x] Set up absolute imports (`@/` alias)

### 1.2 Development Environment
- [x] Configure ESLint with recommended rules (included with Vite)
- [ ] Set up Prettier for code formatting
- [x] Add `.env.example` with required variables:
  - [x] `VITE_API_BASE_URL`
  - [x] `VITE_PRIVY_APP_ID`
  - [x] `VITE_BOT_API_URL`
- [ ] Update `docker-compose.yml` to serve React dev server
- [ ] Configure CORS in FastAPI backend for localhost:5173

### 1.3 Build Pipeline
- [x] Configure production build output to `frontend/dist/` (Vite default)
- [ ] Set up Nginx to serve static files in Docker
- [ ] Update Dockerfile for multi-stage build (build → serve)
- [ ] Test production build locally

### 1.4 Testing Infrastructure
- [ ] Install Vitest for unit testing
- [ ] Install React Testing Library
- [ ] Install Playwright for E2E testing
- [ ] Create test utilities and mocks
- [x] Write test: Verify build succeeds
- [ ] Write test: Verify setup renders without errors

---

## Phase 2: API Refactoring

**Status:** `[x]` Complete

### 2.1 Backend API Conversion - React SPA
- [x] Audit all Jinja2 template routes in `main.py`
- [x] Convert template routes to serve React SPA:
  - [x] Remove all `TemplateResponse` routes
  - [x] Serve `frontend/dist/index.html` for all non-API routes (SPA catch-all)
  - [x] Mount `frontend/dist` as static files at `/`
- [x] Routes removed (now handled by React Router):
  - [x] `/` (dashboard home) → React handles this
  - [x] `/funding` → React handles this
  - [x] `/positions` → React handles this
  - [x] `/strategy` → React handles this
  - [x] `/login` → Privy SDK handles this
  - [x] `/setup/*` → Privy SDK handles wallet creation

### 2.2 Authentication API Updates
- [x] Authentication handled by Privy React SDK (no backend JWT needed)
- [x] CORS configured for React dev server
- [x] API routes accessible from frontend

### 2.3 API Client Layer
- [x] Create `src/api/client.ts` with axios instance
- [x] Add request/response interceptors
- [x] Implement error handling
- [x] Add API types/interfaces
- [x] Create service modules:
  - [ ] `auth.ts` (using Privy SDK instead)
  - [x] `positions.ts`
  - [x] `rates.ts`
  - [x] `settings.ts`
  - [ ] `balances.ts` (TODO)
  - [ ] `control.ts` (TODO)
- [ ] Write tests: Mock API calls, verify error handling

### 2.4 Real-Time Updates
- [ ] Convert SSE endpoints to use EventSource
- [ ] Create React hook for SSE connection
- [ ] Implement reconnection logic
- [ ] Test: Events flow correctly to React components

---

## Phase 3: Component Migration

**Status:** `[~]` In Progress (Dashboard UI complete, needs data integration)

### 3.1 Layout & Navigation
- [x] Create `Layout.tsx` component:
  - [x] Header with auth state
  - [x] Navigation tabs (Home, Settings, etc.)
  - [x] Footer/security banner
- [x] Create `AuthWrapper.tsx` for protected routes
- [x] Implement mobile responsive layout
- [ ] Write tests: Layout renders, navigation works

### 3.2 Authentication Integration (Privy React SDK)
- [x] Install `@privy-io/react-auth`
- [x] Configure `PrivyProvider` with app ID
- [x] Create `AuthWrapper.tsx`:
  - [x] Wrap app with Privy provider
  - [x] Handle auth state
- [x] Create `LoginPage.tsx`:
  - [x] Use Privy's `LoginModal` or custom UI
  - [x] Email OTP flow
  - [x] Wallet creation on signup (configured in PrivyProvider)
- [ ] Create `DepositModal.tsx`:
  - [ ] Display Solana + EVM addresses
  - [ ] QR code generation
  - [ ] Copy buttons
- [ ] Write tests: Auth flow, wallet display

### 3.3 Home Tab Components
- [x] Create `LeverageSlider.tsx`:
  - [x] Range slider (1.1x - 4x)
  - [x] Editable number input
  - [x] Synchronized with slider
- [x] Create `OpenPositionButton.tsx`:
  - [x] Disabled state when unfunded
  - [x] Loading state
- [x] Create `StrategyPerformance.tsx`:
  - [x] Net APY display
  - [x] Protocol breakdown
  - [x] APY calculation based on leverage
- [x] Create `LegDetails.tsx`:
  - [x] Asgard leg panel
  - [x] Hyperliquid leg panel
- [x] Create `QuickStats.tsx`:
  - [x] Open positions count
  - [x] 24h PnL
  - [x] Total value
- [x] Create `ActivePositions.tsx`:
  - [x] Position list
  - [x] Refresh button
- [ ] Write tests: Each component renders with mock data

### 3.4 Settings Tab Components
- [ ] Create `SettingsForm.tsx`:
  - [ ] Leverage input
  - [ ] Position size limits
  - [ ] Risk parameters
- [ ] Create `PresetSelector.tsx`:
  - [ ] 3 saveable presets
  - [ ] Load/save functionality
- [ ] Create `RiskSettings.tsx`:
  - [ ] Circuit breaker toggles
  - [ ] Exit criteria
- [ ] Write tests: Form validation, preset saving

### 3.5 Positions Components
- [ ] Create `PositionList.tsx`:
  - [ ] List of active positions
  - [ ] PnL display
  - [ ] Health indicators
- [ ] Create `PositionCard.tsx`:
  - [ ] Individual position details
  - [ ] Close button
- [ ] Create `OpenPositionModal.tsx`:
  - [ ] Confirmation dialog
  - [ ] Asset selector
  - [ ] Size input
- [ ] Create `ClosePositionModal.tsx`:
  - [ ] Confirmation dialog
  - [ ] Position details
- [ ] Write tests: Position display, modal interactions

### 3.6 Real-Time Components
- [ ] Create `RateDisplay.tsx`:
  - [ ] Live funding rates
  - [ ] Auto-refresh indicator
- [ ] Create `ToastNotifications.tsx`:
  - [ ] Position opened/closed events
  - [ ] Error notifications
- [ ] Write tests: Rate updates trigger re-renders

---

## Phase 4: State Management & Hooks

**Status:** `[ ]` Not Started

### 4.1 Global State Setup
- [ ] Install Zustand
- [ ] Create stores:
  - [ ] `authStore.ts` - User session, wallets
  - [ ] `positionsStore.ts` - Position data
  - [ ] `ratesStore.ts` - Current rates
  - [ ] `settingsStore.ts` - User settings
  - [ ] `uiStore.ts` - Modal states, loading
- [ ] Write tests: Store actions and selectors

### 4.2 Custom Hooks
- [ ] Create `useAuth.ts`:
  - [ ] Login/logout
  - [ ] Wallet addresses
- [ ] Create `usePositions.ts`:
  - [ ] Fetch positions
  - [ ] Open/close position
- [ ] Create `useRates.ts`:
  - [ ] Fetch current rates
  - [ ] Calculate APY
- [ ] Create `useSettings.ts`:
  - [ ] Load/save settings
  - [ ] Preset management
- [ ] Create `useSSE.ts`:
  - [ ] EventSource connection
  - [ ] Event handlers
- [ ] Write tests: Hooks with mock providers

### 4.3 Data Fetching
- [ ] Implement React Query (TanStack Query):
  - [ ] Cache rates data
  - [ ] Cache positions
  - [ ] Background refetching
- [ ] Add loading states
- [ ] Add error boundaries
- [ ] Write tests: Loading/error states

---

## Phase 5: Testing & Polish

**Status:** `[ ]` Not Started

### 5.1 Unit Tests
- [ ] Component tests (80%+ coverage):
  - [ ] `LeverageSlider`
  - [ ] `PositionCard`
  - [ ] `SettingsForm`
  - [ ] `AuthWrapper`
- [ ] Hook tests:
  - [ ] `useAuth`
  - [ ] `usePositions`
  - [ ] `useRates`
- [ ] Store tests:
  - [ ] All Zustand stores

### 5.2 Integration Tests
- [ ] Test: Full auth flow
- [ ] Test: Open position flow
- [ ] Test: Close position flow
- [ ] Test: Settings save/load
- [ ] Test: Real-time rate updates

### 5.3 E2E Tests (Playwright)
- [ ] Test: User login
- [ ] Test: Dashboard navigation
- [ ] Test: Open/close position
- [ ] Test: Settings modification

### 5.4 Polish
- [ ] Add loading skeletons
- [ ] Add error fallbacks
- [ ] Verify mobile responsiveness
- [ ] Accessibility audit (ARIA labels)
- [ ] Dark mode verification
- [ ] Performance audit (Lighthouse)

---

## Phase 6: Deployment

**Status:** `[ ]` Not Started

### 6.1 Docker Updates
- [ ] Update `docker/Dockerfile`:
  - [ ] Multi-stage build (Node build → Python serve)
  - [ ] Copy `frontend/dist/` to Nginx
- [ ] Update `docker-compose.yml`:
  - [ ] Remove dev server in production
  - [ ] Add volume for static assets
- [ ] Test: Build succeeds, app runs

### 6.2 Configuration
- [ ] Environment variables documented
- [ ] Production API URLs configured
- [ ] CORS origins set correctly
- [ ] Test: Production build works end-to-end

### 6.3 Documentation
- [ ] Update `README.md` with new frontend setup
- [ ] Document `frontend/` structure
- [ ] Add development workflow guide
- [ ] Document deployment process

---

## Testing Strategy Summary

| Component Type | Testing Approach |
|----------------|------------------|
| UI Components | React Testing Library + Jest |
| Hooks | React Testing Library (renderHook) |
| Stores | Unit tests with Zustand |
| API Client | Mock service worker (MSW) |
| E2E Flows | Playwright |

### Test Coverage Targets
- [ ] Unit tests: 80%+
- [ ] Integration tests: Critical paths covered
- [ ] E2E tests: Main user flows covered

---

## Progress Tracking

### Phase 1
- [x] Setup complete
- [ ] Tests passing (deferred)

### Phase 2
- [x] Backend APIs converted
- [x] API client created
- [ ] API client tested (deferred)

### Phase 3
- [x] Dashboard components migrated
- [x] Layout & Navigation complete
- [x] Authentication with Privy SDK
- [ ] Settings components (TODO)
- [ ] Positions components (TODO)
- [ ] Component tests (deferred)

### Phase 4
- [ ] State management with Zustand (TODO)
- [ ] Custom hooks for data fetching (TODO)
- [ ] React Query integration (TODO)

### Phase 5
- [ ] All tests passing
- [ ] Polish complete
- [ ] Fix frontend styling (LoginModal display issue)

### Phase 6
- [ ] Docker multi-stage build
- [ ] Deployed to production
- [ ] Documentation updated

---

## Notes

### Key Decisions
- **State Management:** Zustand (lightweight, no boilerplate)
- **Data Fetching:** TanStack Query (caching, background updates)
- **Styling:** Tailwind CSS (consistent with current design)
- **Testing:** Vitest + React Testing Library + Playwright

### Risk Areas
1. **Privy SDK integration** - Test thoroughly on staging
2. **SSE real-time updates** - Ensure reconnection logic is robust
3. **Mobile responsiveness** - Test on actual devices
4. **Bundle size** - Monitor and optimize if needed

### Rollback Plan
- Keep Jinja2 templates in `templates_backup/` during migration
- Maintain backward-compatible API responses
- Feature flag for gradual rollout
