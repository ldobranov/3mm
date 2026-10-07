import axios from 'axios';
import type { AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';
import { getToken, refreshToken, clearAuth } from '@/utils/auth';
import { getBackendUrl, invalidateRuntimeConfig, setBackendOverride, clearBackendOverride } from './runtime-config';
import { getExtensionCatalog, invalidateExtensionCatalog, peekPublicEndpoints, isPublicEndpoint } from './extension-catalog';

// Custom JSON stringify that preserves Unicode characters
function stringifyPreserveUnicode(obj: any): string {
  if (obj === null || obj === undefined) {
    return 'null';
  }

  if (typeof obj === 'string') {
    // For strings, wrap in quotes but don't escape Unicode
    // Must still escape JSON control characters (newlines, tabs, etc.)
    // otherwise we can produce invalid JSON (causing backend 422 json_invalid).
    return (
      '"' +
      obj
        .replace(/\\/g, '\\\\')
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r')
        .replace(/\t/g, '\\t')
        .replace(/\f/g, '\\f')
        // Backspace (U+0008) must be escaped; use a character class because /\b/ is a word-boundary regex.
        .replace(/[\b]/g, '\\b') +
      '"'
    );
  }

  if (typeof obj === 'number' || typeof obj === 'boolean') {
    return String(obj);
  }

  if (Array.isArray(obj)) {
    const items = obj.map(item => stringifyPreserveUnicode(item));
    return '[' + items.join(',') + ']';
  }

  if (typeof obj === 'object') {
    const pairs = [];
    for (const key in obj) {
      if (obj.hasOwnProperty(key)) {
        const value = stringifyPreserveUnicode(obj[key]);
        pairs.push('"' + key + '":' + value);
      }
    }
    return '{' + pairs.join(',') + '}';
  }

  return 'null';
}

// Extend AxiosRequestConfig to include _retry property
interface AxiosConfig extends AxiosRequestConfig {
  _retry?: boolean;
  _networkRetry?: boolean;
}

// Create the dynamic HTTP client
const createDynamicHttpClient = async () => {
  const baseURL = await getBackendUrl();
  // console.log('Creating HTTP client with baseURL:', baseURL);

  // Configure Axios to preserve Unicode characters
  const instance = axios.create({
    baseURL,
    // Custom transformRequest to preserve Unicode
    transformRequest: [(data, headers) => {
      // Skip transformation for FormData
      if (data instanceof FormData) {
        return data;
      }
      if (data && typeof data === 'object') {
        headers['Content-Type'] = 'application/json';
        // Use custom Unicode-preserving stringify
        return stringifyPreserveUnicode(data);
      }
      return data;
    }]
  });

  return instance;
};

// Single-flight creation; URL changes invalidate both discovery and transport.
let httpInstance: any = null;
let httpPromise: Promise<any> | null = null;
let transportGeneration = 0;
function resetTransport() {
  ++transportGeneration;
  httpInstance = httpPromise = null;
  invalidateExtensionCatalog();
}
async function getHttpInstance(): Promise<any> {
  if (httpInstance) return httpInstance;
  if (httpPromise) return httpPromise;
  const generation = transportGeneration;
  const request = createDynamicHttpClient().then(instance => {
    if (generation !== transportGeneration) return getHttpInstance();
    setupInterceptors(instance);
    httpInstance = instance;
    return instance;
  }).finally(() => { if (httpPromise === request) httpPromise = null; });
  httpPromise = request;
  return request;
}

// Setup request/response interceptors
function setupInterceptors(http: any) {
  // Request interceptor
  http.interceptors.request.use((config: AxiosConfig) => {
    const publicRequest = isPublicEndpoint(config.url || '');
    if (!publicRequest) {
      const token = getToken();
      if (token) {
        config.headers = config.headers || {};
        (config.headers as any).Authorization = `Bearer ${token}`;
      }
    }
    return config;
  });

  // Response interceptor with token refresh logic
  let isRefreshing = false;
  let queued: Array<(token: string | null) => void> = [];

  http.interceptors.response.use(
    (res: AxiosResponse) => res,
    async (error: AxiosError) => {
      const status = error?.response?.status;
      const original = error.config as AxiosConfig;

      if (status === 401 && original && !original._retry && getToken() && !isPublicEndpoint(original.url || '')) {
        if (!isRefreshing) {
          isRefreshing = true;
          try {
            const ok = await refreshToken();
            isRefreshing = false;
            queued.forEach((cb) => cb(ok ? getToken() : null));
            queued = [];
            
            if (ok && original) {
              original._retry = true;
              original.headers = original.headers || {};
              original.headers.Authorization = `Bearer ${getToken()}`;
              return http(original);
            } else {
              alert('Your session has expired. Please log in again.');
              clearAuth();
              window.location.replace('/user/login');
              return Promise.reject(error);
            }
          } catch (refreshError) {
            isRefreshing = false;
            queued.forEach((cb) => cb(null));
            queued = [];
            
            alert('Your session has expired. Please log in again.');
            clearAuth();
            window.location.replace('/user/login');
            return Promise.reject(refreshError);
          }
        }

        return new Promise((resolve, reject) => {
          queued.push((newToken) => {
            if (newToken && original) {
              original._retry = true;
              original.headers = original.headers || {};
              original.headers.Authorization = `Bearer ${newToken}`;
              resolve(http(original));
            } else {
              reject(error);
            }
          });
        });
      }

      // No discovery from interceptors, and never replay an uncertain mutation.
      if (original && (error.code === 'ERR_NETWORK' || error.code === 'ECONNREFUSED')
          && !original._networkRetry && ['get', 'head'].includes((original.method || 'get').toLowerCase())) {
        original._networkRetry = true;
        return http(original);
      }

      return Promise.reject(error);
    }
  );
}

// Export the dynamic HTTP instance
export default {
  async get(url: string, config?: AxiosRequestConfig) {
    const http = await getHttpInstance();
    return http.get(url, config);
  },
  
  async post(url: string, data?: any, config?: AxiosRequestConfig) {
    // console.log('Dynamic HTTP POST request to:', url, 'with data:', data);
    try {
      const http = await getHttpInstance();
      // console.log('HTTP instance baseURL:', http.defaults.baseURL);
      const result = await http.post(url, data, config);
      // console.log('Dynamic HTTP POST response:', result);
      return result;
    } catch (error: any) {
      console.error('Dynamic HTTP POST error:', error);
      console.error('Error details:', {
        message: error.message,
        code: error.code,
        status: error.response?.status,
        url: error.config?.url
      });
      throw error;
    }
  },
  
  async put(url: string, data?: any, config?: AxiosRequestConfig) {
    const http = await getHttpInstance();
    return http.put(url, data, config);
  },
  
  async patch(url: string, data?: any, config?: AxiosRequestConfig) {
    const http = await getHttpInstance();
    return http.patch(url, data, config);
  },
  
  async delete(url: string, config?: AxiosRequestConfig) {
    const http = await getHttpInstance();
    return http.delete(url, config);
  },
  
  async request(config: AxiosRequestConfig) {
    const http = await getHttpInstance();
    return http.request(config);
  },
  
  // Utility methods
  async getCurrentBackendUrl(): Promise<string> {
    return await getBackendUrl();
  },

  async refreshBackendUrl(): Promise<string> {
    invalidateRuntimeConfig();
    resetTransport();
    return await getBackendUrl();
  },

  /**
   * Persistently overrides the backend URL (stored in localStorage) and immediately updates
   * the currently cached Axios instance (so the change takes effect without reload).
   *
   * Pass "" to use proxy/same-origin routing.
   */
  async setBackendUrlOverride(url: string): Promise<string> {
    const normalized = setBackendOverride(url);
    resetTransport();
    return normalized;
  },

  /**
   * Clears any persistent backend URL override and invalidates the current client.
   * Detection is deliberately deferred until the next request so this recovery
   * action cannot hang while trying to contact an unreachable backend.
   */
  async clearBackendUrlOverride(): Promise<string> {
    clearBackendOverride();
    resetTransport();
    return '';
  },

  async getPublicEndpoints(): Promise<string[]> {
    try { await getExtensionCatalog(); } catch { /* Cached policy/defaults remain usable. */ }
    return peekPublicEndpoints();
  },

  async refreshPublicEndpoints(): Promise<string[]> {
    try { await getExtensionCatalog(true); } catch { /* Bounded retry backoff. */ }
    return peekPublicEndpoints();
  },
  
  // For backward compatibility with existing code
  create(config: AxiosRequestConfig) {
    return axios.create(config);
  }
};
