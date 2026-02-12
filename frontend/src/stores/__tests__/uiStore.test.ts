import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useUIStore } from '../uiStore';

describe('uiStore', () => {
  beforeEach(() => {
    const store = useUIStore.getState();
    store.closeModal();
    store.toasts.forEach((t) => store.removeToast(t.id));
    store.setGlobalLoading(false);
    store.setSidebarOpen(false);
  });

  it('should have correct initial state', () => {
    const state = useUIStore.getState();
    expect(state.activeModal).toBeNull();
    expect(state.toasts).toEqual([]);
    expect(state.globalLoading).toBe(false);
    expect(state.sidebarOpen).toBe(false);
  });

  it('should open and close modal', () => {
    const store = useUIStore.getState();
    const modalData = { positionId: '123' };

    store.openModal('openPosition', modalData);

    let state = useUIStore.getState();
    expect(state.activeModal).toBe('openPosition');
    expect(state.modalData).toEqual(modalData);

    store.closeModal();

    state = useUIStore.getState();
    expect(state.activeModal).toBeNull();
    expect(state.modalData).toBeNull();
  });

  it('should add toast', () => {
    const store = useUIStore.getState();
    store.addToast('Test message', 'success');

    const state = useUIStore.getState();
    expect(state.toasts).toHaveLength(1);
    expect(state.toasts[0].message).toBe('Test message');
    expect(state.toasts[0].type).toBe('success');
  });

  it('should remove toast', () => {
    const store = useUIStore.getState();
    store.addToast('Test message', 'info');
    const toastId = useUIStore.getState().toasts[0].id;

    store.removeToast(toastId);

    const state = useUIStore.getState();
    expect(state.toasts).toHaveLength(0);
  });

  it('should auto-remove toast after duration', async () => {
    vi.useFakeTimers();
    const store = useUIStore.getState();
    
    store.addToast('Test message', 'info', 1000);
    expect(useUIStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(1000);

    expect(useUIStore.getState().toasts).toHaveLength(0);
    vi.useRealTimers();
  });

  it('should set global loading', () => {
    const store = useUIStore.getState();
    
    store.setGlobalLoading(true, 'Loading data...');

    let state = useUIStore.getState();
    expect(state.globalLoading).toBe(true);
    expect(state.loadingMessage).toBe('Loading data...');

    store.setGlobalLoading(false);

    state = useUIStore.getState();
    expect(state.globalLoading).toBe(false);
  });

  it('should toggle sidebar', () => {
    const store = useUIStore.getState();
    expect(store.sidebarOpen).toBe(false);

    store.toggleSidebar();
    expect(useUIStore.getState().sidebarOpen).toBe(true);

    store.toggleSidebar();
    expect(useUIStore.getState().sidebarOpen).toBe(false);
  });

  it('should set sidebar open state', () => {
    const store = useUIStore.getState();
    
    store.setSidebarOpen(true);
    expect(useUIStore.getState().sidebarOpen).toBe(true);

    store.setSidebarOpen(false);
    expect(useUIStore.getState().sidebarOpen).toBe(false);
  });
});
