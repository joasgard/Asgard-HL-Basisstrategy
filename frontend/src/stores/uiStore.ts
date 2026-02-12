import { create } from 'zustand';

export type ModalType = 
  | 'deposit' 
  | 'openPosition' 
  | 'closePosition' 
  | 'settings' 
  | 'withdraw' 
  | null;

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
  // Error-specific fields
  errorCode?: string;
  errorDescription?: string;
  docsUrl?: string;
}

interface UIState {
  // Modals
  activeModal: ModalType;
  modalData: unknown;
  
  // Toasts
  toasts: Toast[];
  
  // Loading states
  globalLoading: boolean;
  loadingMessage: string;
  
  // Sidebar/Mobile
  sidebarOpen: boolean;
  
  // Actions
  openModal: (modal: ModalType, data?: unknown) => void;
  closeModal: () => void;
  addToast: (message: string, type: ToastType, duration?: number) => void;
  addErrorToast: (params: {
    title: string;
    message: string;
    code: string;
    docsUrl?: string;
    duration?: number;
  }) => void;
  removeToast: (id: string) => void;
  setGlobalLoading: (value: boolean, message?: string) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (value: boolean) => void;
}

export const useUIStore = create<UIState>((set, get) => ({
  activeModal: null,
  modalData: null,
  toasts: [],
  globalLoading: false,
  loadingMessage: '',
  sidebarOpen: false,

  openModal: (modal, data) => set({ activeModal: modal, modalData: data }),
  closeModal: () => set({ activeModal: null, modalData: null }),

  addToast: (message, type, duration = 5000) => {
    const id = Math.random().toString(36).substring(7);
    const toast: Toast = { id, message, type, duration };
    set((state) => ({ toasts: [...state.toasts, toast] }));
    
    // Auto-remove toast after duration
    setTimeout(() => {
      get().removeToast(id);
    }, duration);
  },

  addErrorToast: ({ title, message, code, docsUrl, duration = 8000 }) => {
    const id = Math.random().toString(36).substring(7);
    const toast: Toast = {
      id,
      message: title,
      type: 'error',
      duration,
      errorCode: code,
      errorDescription: message,
      docsUrl,
    };
    set((state) => ({ toasts: [...state.toasts, toast] }));
    
    // Auto-remove toast after duration
    setTimeout(() => {
      get().removeToast(id);
    }, duration);
  },

  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }));
  },

  setGlobalLoading: (value, message = '') => {
    set({ globalLoading: value, loadingMessage: message });
  },

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (value) => set({ sidebarOpen: value }),
}));
