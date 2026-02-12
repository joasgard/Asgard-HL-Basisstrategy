import { useEffect, useRef, useCallback } from 'react';
import { usePositionsStore, useRatesStore, useUIStore } from '../stores';

interface SSEMessage {
  type: 'position_update' | 'rate_update' | 'error' | 'connected';
  data: unknown;
  timestamp: string;
}

export function useSSE() {
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  
  const updatePosition = usePositionsStore((s) => s.updatePosition);
  const setRates = useRatesStore((s) => s.setRates);
  const addToast = useUIStore((s) => s.addToast);

  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_DELAY = 3000; // 3 seconds

  const connect = useCallback(() => {
    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const apiUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';
    // Backend SSE endpoint is at /api/v1/events/stream
    const sseUrl = `${apiUrl}/events/stream`;
    
    try {
      const eventSource = new EventSource(sseUrl);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        console.log('SSE connection established');
        reconnectAttemptsRef.current = 0;
      };

      eventSource.onmessage = (event) => {
        try {
          const message: SSEMessage = JSON.parse(event.data);
          
          switch (message.type) {
            case 'position_update':
              if (typeof message.data === 'object' && message.data) {
                const position = message.data as { id: string };
                updatePosition(position.id, message.data);
              }
              break;
              
            case 'rate_update':
              if (typeof message.data === 'object' && message.data) {
                setRates(message.data as Parameters<typeof setRates>[0]);
              }
              break;
              
            case 'error':
              console.error('SSE error message:', message.data);
              break;
              
            case 'connected':
              console.log('SSE connected:', message.data);
              break;
          }
        } catch (error) {
          console.error('Failed to parse SSE message:', error);
        }
      };

      eventSource.onerror = (error) => {
        console.error('SSE error:', error);
        eventSource.close();
        
        // Attempt reconnection
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current++;
          const delay = RECONNECT_DELAY * reconnectAttemptsRef.current;
          
          console.log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        } else {
          addToast('Real-time updates disconnected. Please refresh the page.', 'error');
        }
      };
    } catch (error) {
      console.error('Failed to create SSE connection:', error);
    }
  }, [updatePosition, setRates, addToast]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    
    reconnectAttemptsRef.current = 0;
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();
    
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    isConnected: !!eventSourceRef.current && eventSourceRef.current.readyState === EventSource.OPEN,
    reconnectAttempts: reconnectAttemptsRef.current,
    connect,
    disconnect,
  };
}
