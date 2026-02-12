import axios from 'axios';
import { parseApiError, formatErrorWithCode } from '../lib/errorCodes';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export interface ApiError {
  code: string;
  message: string;
  description: string;
  httpStatus: number;
  docsUrl?: string;
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
  withCredentials: true,
});

/**
 * Transform an axios error into our standard ApiError format.
 */
function transformError(error: unknown): ApiError {
  // Check if it's an axios error with response
  if (axios.isAxiosError(error) && error.response?.data) {
    const responseData = error.response.data;
    
    // Backend error format with error_code
    if (responseData.error_code) {
      const parsed = parseApiError(responseData);
      return {
        code: parsed.code,
        message: parsed.message,
        description: parsed.description,
        httpStatus: error.response.status,
        docsUrl: `https://docs.asgard.finance/errors/${parsed.code.toLowerCase()}`,
      };
    }
    
    // Simple message format
    if (responseData.message) {
      return {
        code: 'GEN-0001',
        message: responseData.message,
        description: 'An error occurred while processing your request.',
        httpStatus: error.response.status,
      };
    }

    // FastAPI detail format (e.g. {"detail": "Not authenticated"})
    if (responseData.detail) {
      return {
        code: 'GEN-0001',
        message: responseData.detail,
        description: responseData.detail,
        httpStatus: error.response.status,
      };
    }

    // Response exists but unrecognized format — preserve actual status
    return {
      code: 'GEN-0001',
      message: error.message || 'Request failed',
      description: 'An error occurred while processing your request.',
      httpStatus: error.response.status,
    };
  }

  // Network errors (no response)
  if (axios.isAxiosError(error) && !error.response) {
    if (error.code === 'ECONNABORTED') {
      return {
        code: 'GEN-0004',
        message: 'Request timed out',
        description: 'The operation took too long. Please try again.',
        httpStatus: 504,
      };
    }
    return {
      code: 'NET-0001',
      message: 'Network error',
      description: 'A network error occurred. Please check your internet connection.',
      httpStatus: 503,
    };
  }

  // Fallback — no response at all
  const parsed = parseApiError(error);
  return {
    code: parsed.code,
    message: parsed.message,
    description: parsed.description,
    httpStatus: 500,
  };
}

// Cookie-based auth - no need to manually set Authorization header
// Cookies are sent automatically with withCredentials: true
apiClient.interceptors.request.use(
  (config) => {
    // Cookies are handled automatically by the browser
    return config;
  },
  (error) => {
    return Promise.reject(transformError(error));
  }
);

// Response interceptor - handle errors and transform to standard format
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const transformedError = transformError(error);
    
    // Handle specific status codes
    if (transformedError.httpStatus === 401) {
      // Cookie-based auth: 401 means session expired
      // The UI should redirect to login
    }
    
    return Promise.reject(transformedError);
  }
);

/**
 * Format an error for display in the UI.
 * Returns a user-friendly title and message.
 */
export function formatErrorForDisplay(error: unknown): { 
  title: string; 
  message: string;
  code: string;
  docsUrl?: string;
} {
  // Check if it's already an ApiError (from our transformError)
  if (error && typeof error === 'object' && 'httpStatus' in error) {
    const apiError = error as ApiError;
    return {
      title: `${apiError.message} (${apiError.code})`,
      message: apiError.description,
      code: apiError.code,
      docsUrl: apiError.docsUrl,
    };
  }
  
  const parsed = parseApiError(error);
  const formatted = formatErrorWithCode(parsed.code);
  
  return {
    title: formatted.title,
    message: parsed.description,
    code: parsed.code,
    docsUrl: formatted.docsUrl,
  };
}

export default apiClient;
