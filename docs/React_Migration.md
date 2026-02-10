# React Migration Plan

**Status:** Not Started  
**Started:** TBD  
**Target Completion:** TBD  
**Assigned:** TBD

---

## Overview

Migrating the Delta Neutral Bot dashboard from server-rendered Jinja2 templates to a React SPA with TypeScript.

### Goals
- Integrate Privy's React SDK for native auth flow
- Modern component-based architecture
- TypeScript for type safety
- Maintain all existing functionality

---

## Phase 1: Setup & Infrastructure

**Status:** `[ ]` Not Started

### 1.1 Project Setup
- [ ] Create `frontend/` directory at project root
- [ ] Initialize Vite + React + TypeScript project
- [ ] Install core dependencies:
  - [ ] React 18
  - [ ] React Router DOM v6
  - [ ] TypeScript
  - [ ] Vite
  - [ ] Tailwind CSS
- [ ] Configure `tsconfig.json` with strict mode
- [ ] Set up absolute imports (`@/` alias)

### 1.2 Development Environment
- [ ] Configure ESLint with recommended rules
- [ ] Set up Prettier for code formatting
- [ ] Add `.env.example` with required variables:
  - [ ] `VITE_API_BASE_URL`
  - [ ] `VITE_PRIVY_APP_ID`
  - [ ] `VITE_BOT_API_URL`
- [ ] Update `docker-compose.yml` to serve React dev server
- [ ] Configure CORS in FastAPI backend for localhost:5173

### 1.3 Build Pipeline
- [ ] Configure production build output to `frontend/dist/`
- [ ] Set up Nginx to serve static files in Docker
- [ ] Update Dockerfile for multi-stage build (build → serve)
- [ ] Test production build locally

### 1.4 Testing Infrastructure
- [ ] Install Vitest for unit testing
- [ ] Install React Testing Library
- [ ] Install Playwright for E2E testing
- [ ] Create test utilities and mocks
- [ ] Write test: Verify setup renders without errors

---

## Phase 2: API Refactoring

**Status:** `[ ]` Not Started

### 2.1 Backend API Conversion
- [ ] Audit all Jinja2 template routes in `main.py`
- [ ] Convert each route to JSON API:
  - [ ] Remove `TemplateResponse` returns
  - [ ] Add proper JSON response models
  - [ ] Keep existing business logic
- [ ] Routes to convert:
  - [ ] `/` (dashboard home)
  - [ ] `/funding` (funding rates page)
  - [ ] `/positions` (positions page)
  - [ ] `/strategy` (strategy page)
  - [ ] `/setup/*` (setup wizard pages)

### 2.2 Authentication API Updates
- [ ] Update `/api/v1/auth/me` to return full user object
- [ ] Add JWT token refresh endpoint
- [ ] Create auth middleware for API routes
- [ ] Test: Auth flow returns valid tokens

### 2.3 API Client Layer
- [ ] Create `src/api/client.ts` with axios instance
- [ ] Add request/response interceptors
- [ ] Implement error handling
- [ ] Add API types/interfaces
- [ ] Create service modules:
  - [ ] `auth.ts`
  - [ ] `positions.ts`
  - [ ] `rates.ts`
  - [ ] `settings.ts`
  - [ ] `balances.ts`
  - [ ] `control.ts`
- [ ] Write tests: Mock API calls, verify error handling

### 2.4 Real-Time Updates
- [ ] Convert SSE endpoints to use EventSource
- [ ] Create React hook for SSE connection
- [ ] Implement reconnection logic
- [ ] Test: Events flow correctly to React components

---

## Phase 3: Component Migration

**Status:** `[ ]` Not Started

### 3.1 Layout & Navigation
- [ ] Create `Layout.tsx` component:
  - [ ] Header with auth state
  - [ ] Navigation tabs (Home, Settings, etc.)
  - [ ] Footer/security banner
- [ ] Create `ProtectedRoute.tsx` wrapper
- [ ] Implement mobile responsive layout
- [ ] Write tests: Layout renders, navigation works

### 3.2 Authentication Integration (Privy React SDK)
- [ ] Install `@privy-io/react-auth`
- [ ] Configure `PrivyProvider` with app ID
- [ ] Create `AuthWrapper.tsx`:
  - [ ] Wrap app with Privy provider
  - [ ] Handle auth state
- [ ] Create `LoginPage.tsx`:
  - [ ] Use Privy's `LoginModal` or custom UI
  - [ ] Email OTP flow
  - [ ] Wallet creation on signup
- [ ] Create `DepositModal.tsx`:
  - [ ] Display Solana + EVM addresses
  - [ ] QR code generation
  - [ ] Copy buttons
- [ ] Write tests: Auth flow, wallet display

### 3.3 Home Tab Components
- [ ] Create `LeverageSlider.tsx`:
  - [ ] Range slider (1.1x - 4x)
  - [ ] Editable number input
  - [ ] Synchronized with slider
- [ ] Create `OpenPositionButton.tsx`:
  - [ ] Disabled state when unfunded
  - [ ] Loading state
- [ ] Create `StrategyPerformance.tsx`:
  - [ ] Net APY display
  - [ ] Protocol breakdown
  - [ ] APY calculation based on leverage
- [ ] Create `LegDetails.tsx`:
  - [ ] Asgard leg panel
  - [ ] Hyperliquid leg panel
- [ ] Create `QuickStats.tsx`:
  - [ ] Open positions count
  - [ ] 24h PnL
  - [ ] Total value
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
- [ ] Setup complete
- [ ] Tests passing

### Phase 2
- [ ] Backend APIs converted
- [ ] API client tested

### Phase 3
- [ ] All components migrated
- [ ] Component tests passing

### Phase 4
- [ ] State management working
- [ ] Custom hooks tested

### Phase 5
- [ ] All tests passing
- [ ] Polish complete

### Phase 6
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
