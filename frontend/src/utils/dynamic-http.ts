import axios from 'axios';
import type { AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';
import { getToken, refreshToken, clearAuth } from '@/utils/auth';

const STORAGE_KEY_BACKEND_URL_OVERRIDE = 'mm_backend_url_override';

function normalizeBaseUrl(url: string): string {
  // Allow "" (proxy routing) explicitly.
  const trimmed = (url ?? '').trim();
  if (trimmed === '') return '';
  return trimmed.replace(/\/+$/, '');
}

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
}

// Cache for the backend URL configuration
let backendUrlCache: string | null = null;
let cacheTimestamp = 0;
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

// Cache for public endpoints
let publicEndpointsCache: string[] = [];
let publicEndpointsTimestamp = 0;
const PUBLIC_ENDPOINTS_CACHE_DURATION = 10 * 60 * 1000; // 10 minutes

// Default fallback URLs
const FALLBACK_URLS = [
  (globalThis as any).__BACKEND_URL__ || 'http://localhost:8887',
  window.location.origin.replace(':5173', ':8887'), // Try same host with backend port
  window.location.origin.replace(':3000', ':8887'),  // Try same host with common dev port
];

// Get public endpoints from installed extensions
async function getPublicEndpoints(): Promise<string[]> {
  const now = Date.now();

  // Return cached endpoints if still valid
  if (publicEndpointsCache.length > 0 && (now - publicEndpointsTimestamp) < PUBLIC_ENDPOINTS_CACHE_DURATION) {
    return publicEndpointsCache;
  }

  try {
    // Load installed extensions (use resolved backend URL, not always same-origin)
    const baseURL = await getBackendUrl();
    const url = baseURL ? `${baseURL}/api/extensions/public` : '/api/extensions/public';
    const response = await fetch(url);
    if (response.ok) {
      const data = await response.json();
      const extensions = data.items || data; // Handle both {items: [...]} and [...] formats

      const publicEndpoints: string[] = [];

      // Always include the extensions public endpoint itself
      publicEndpoints.push('/api/extensions/public');

      // Check each extension for public endpoints
      for (const extension of extensions) {
        // Check if extension has public routes
        if (extension.frontend_routes) {
          for (const route of extension.frontend_routes) {
            if (route.meta && route.meta.requiresAuth === false) {
              // Convert frontend route to API route pattern
              const apiRoute = route.path.replace(/^\/extension/, `/api/extension/${extension.name}`);
              publicEndpoints.push(apiRoute);
              publicEndpoints.push(`${apiRoute}/*`); // Include sub-routes
            }
          }
        }

        // Check extension-specific public API patterns
        // For now, we'll use heuristics based on extension name and type
        if (extension.type === 'extension' || extension.type === 'widget') {
          // Assume store-like extensions have public APIs
          if (extension.name.toLowerCase().includes('store') ||
              extension.name.toLowerCase().includes('shop') ||
              extension.name.toLowerCase().includes('market')) {
            publicEndpoints.push(`/api/${extension.name.toLowerCase()}/*`);
          }
        }
      }

      // Cache the results
      publicEndpointsCache = publicEndpoints;
      publicEndpointsTimestamp = now;
      
      return publicEndpoints;
    }
  } catch (error) {
    console.warn('Failed to load public endpoints, using defaults:', error);
  }

  // Fallback to basic defaults
  const defaults = ['/api/extensions/public', '/api/store/*'];
  publicEndpointsCache = defaults;
  publicEndpointsTimestamp = now;
  return defaults;
}

// Get backend URL from cache or detect from current location
async function getBackendUrl(): Promise<string> {
  const now = Date.now();

  // 1) Runtime config (frontend-hosted) - preferred for split-origin production deployments.
  // Served from the frontend host, so it is available even when the backend URL is unknown.
  try {
    const res = await fetch('/runtime-config.json', { cache: 'no-store' });
    if (res.ok) {
      const cfg = await res.json();
      if (cfg?.backend_url) {
        const normalized = normalizeBaseUrl(String(cfg.backend_url));
        backendUrlCache = normalized;
        cacheTimestamp = now;
        return normalized;
      }
    }
  } catch {
    // Ignore runtime-config load errors and continue with fallbacks.
  }

  // 2) User override (safe-mode fallback)
  // Note: localStorage returns string | null; empty string is a valid value (proxy routing).
  try {
    const override = localStorage.getItem(STORAGE_KEY_BACKEND_URL_OVERRIDE);
    if (override !== null) {
      const normalized = normalizeBaseUrl(override);
      backendUrlCache = normalized;
      cacheTimestamp = now;
      return normalized;
    }
  } catch {
    // Ignore localStorage access errors (private mode / denied)
  }

  // Return cached URL if still valid
  if (backendUrlCache && (now - cacheTimestamp) < CACHE_DURATION) {
    // console.log('Using cached backend URL:', backendUrlCache);
    return backendUrlCache;
  }

  // Try to load settings from backend to get configured backend URL
  // console.log('Loading settings from backend to determine correct backend URL');

  try {
    // Try to load settings from backend
    const response = await fetch('/frontend-config');
    if (response.ok) {
      const config = await response.json();
      if (config.backend_url) {
        // console.log('Using backend URL from settings:', config.backend_url);
        backendUrlCache = normalizeBaseUrl(String(config.backend_url));
        cacheTimestamp = now;
        return backendUrlCache;
      }
    }
  } catch (error) {
    console.log('Could not load settings, trying network discovery:', error);
  }

  try {
    // Try network discovery for mobile access
    const discoveredUrl = await discoverBackendUrl();
    backendUrlCache = discoveredUrl;
    cacheTimestamp = now;
    return discoveredUrl;
  } catch (error) {
    console.warn('Network discovery failed, using fallback detection:', error);
  }

  // Fallback: try to detect from current location
  const detectedUrl = detectBackendUrl();
  console.log('Using detected backend URL:', detectedUrl);
  backendUrlCache = detectedUrl;
  cacheTimestamp = now;
  console.log('Backend URL detection completed successfully');
  return detectedUrl;
}

// Enhanced backend URL detection with mobile support
function detectBackendUrl(): string {
  const protocol = window.location.protocol;
  const hostname = window.location.hostname;
  const port = window.location.port;
  
  // If running on localhost, use empty string for proxy routing
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    console.log('Running on localhost, using proxy routing');
    return '';
  }
  
  // Mobile device detection and special handling
  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  const isNetworkRequest = hostname.match(/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/); // IP address
  
  // If running on an IP address (common in mobile access scenarios)
  if (isNetworkRequest) {
    // For IP-based access, use the same IP with backend port
    const backendUrl = (globalThis as any).__BACKEND_URL__ || 'http://localhost:8887';
    const url = new URL(backendUrl);
    return `${protocol}//${hostname}:${url.port}`;
  }
  
  // For development with Vite proxy, use empty string for localhost
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return '';
  }

  const backendPort = new URL((globalThis as any).__BACKEND_URL__ || 'http://localhost:8887').port || '8887';

  // If running on a different port, try the same host with backend port
  if (port && port !== backendPort) {
    // Special handling for mobile browsers that might have port restrictions
    if (isMobile) {
      // Try common mobile-friendly ports first
      return `${protocol}//${hostname}:${backendPort}`;
    }
    return `${protocol}//${hostname}:${backendPort}`;
  }

  // If running on standard ports, try the same host
  // For mobile, ensure we're using a reachable port
  if (isMobile && port === '5173') {
    // Mobile devices accessing frontend on 5173 should connect to backend on configured port
    return `${protocol}//${hostname}:${backendPort}`;
  }

  return `${protocol}//${hostname}:${backendPort}`;
}

// Network discovery for mobile devices
async function discoverBackendUrl(): Promise<string> {
  const hostname = window.location.hostname;
  const protocol = window.location.protocol;

  console.log('Starting network discovery for hostname:', hostname, 'protocol:', protocol);

  // For development environments (localhost, 127.0.0.1), always use proxy
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    console.log('Development environment detected, using proxy routing');
    return '';
  }

  // For IP addresses (like 192.168.x.x), try direct connection first
  if (hostname.match(/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/)) {
    try {
      const backendPort = new URL((globalThis as any).__BACKEND_URL__ || 'http://localhost:8887').port || '8887';
      const testUrl = `${protocol}//${hostname}:${backendPort}`;
      console.log('Testing direct backend URL for IP address:', testUrl);

      // Use AbortController for timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);

      const response = await fetch(testUrl + '/docs', {
        method: 'GET',
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        console.log('Backend URL test successful:', testUrl);
        return testUrl;
      } else {
        console.log('Backend responded but not OK, status:', response.status);
      }
    } catch (error) {
      console.log('Direct backend connection failed for IP address, falling back to proxy:', error);
    }
  }

  // For other hostnames, try direct connection
  if (hostname && hostname !== 'localhost' && hostname !== '127.0.0.1') {
    try {
      const backendPort = new URL((globalThis as any).__BACKEND_URL__ || 'http://localhost:8887').port || '8887';
      const testUrl = `${protocol}//${hostname}:${backendPort}`;
      console.log('Testing backend URL for hostname:', testUrl);

      // Use AbortController for timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);

      const response = await fetch(testUrl + '/docs', {
        method: 'GET',
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        console.log('Backend URL test successful:', testUrl);
        return testUrl;
      } else {
        console.log('Backend responded but not OK, status:', response.status);
      }
    } catch (error) {
      console.log('Direct backend connection failed, falling back to proxy:', error);
    }
  }

  // Fallback to proxy routing for development/production
  console.log('Using proxy routing as fallback');
  return '';
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

// Cache the HTTP client instance
let httpInstance: any = null;
let isCreatingInstance = false;

// Get or create HTTP instance
async function getHttpInstance() {
  if (httpInstance && !httpInstance.isRefreshing) {
    return httpInstance;
  }
  
  if (isCreatingInstance) {
    // Wait for existing instance creation
    return new Promise((resolve) => {
      const checkInstance = () => {
        if (httpInstance) {
          resolve(httpInstance);
        } else {
          setTimeout(checkInstance, 100);
        }
      };
      checkInstance();
    });
  }
  
  isCreatingInstance = true;
  try {
    httpInstance = await createDynamicHttpClient();
    setupInterceptors(httpInstance);
    return httpInstance;
  } finally {
    isCreatingInstance = false;
  }
}

// Setup request/response interceptors
function setupInterceptors(http: any) {
  // Request interceptor
  http.interceptors.request.use(async (config: AxiosConfig) => {
    // Get dynamic list of public endpoints
    const publicEndpoints = await getPublicEndpoints();

    // Check if current URL matches any public endpoint pattern
    const isPublicEndpoint = config.url && publicEndpoints.some(pattern => {
      if (pattern.endsWith('/*')) {
        // Wildcard pattern - check if URL starts with the pattern (without /*)
        const basePattern = pattern.slice(0, -2);
        return config.url!.startsWith(basePattern);
      } else {
        // Exact match
        return config.url === pattern;
      }
    });

    if (!isPublicEndpoint) {
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

      if ((status === 401 || status === 403) && !original._retry) {
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

      // If we get a network error, it might be due to wrong backend URL
      if (error.code === 'ERR_NETWORK' || error.code === 'ECONNREFUSED') {
        console.warn('Network error - backend might be unavailable at:', error.config?.baseURL);
        
        // Try to refresh the backend URL and retry once
        backendUrlCache = null; // Clear cache
        cacheTimestamp = 0;
        
        try {
          const newHttpInstance = await createDynamicHttpClient();
          setupInterceptors(newHttpInstance);
          httpInstance = newHttpInstance;
          
          // Retry the request with new backend URL
          if (original) {
            const retryConfig = {
              ...original,
              baseURL: newHttpInstance.defaults.baseURL
            };
            return newHttpInstance(retryConfig);
          }
        } catch (retryError) {
          console.error('Failed to retry with new backend URL:', retryError);
        }
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
        response: error.response,
        config: error.config
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
    backendUrlCache = null;
    cacheTimestamp = 0;
    return await getBackendUrl();
  },

  /**
   * Persistently overrides the backend URL (stored in localStorage) and immediately updates
   * the currently cached Axios instance (so the change takes effect without reload).
   *
   * Pass "" to use proxy/same-origin routing.
   */
  async setBackendUrlOverride(url: string): Promise<string> {
    const normalized = normalizeBaseUrl(url);
    try {
      localStorage.setItem(STORAGE_KEY_BACKEND_URL_OVERRIDE, normalized);
    } catch {
      // Ignore
    }
    backendUrlCache = normalized;
    cacheTimestamp = Date.now();
    if (httpInstance) {
      httpInstance.defaults.baseURL = normalized;
    }
    return normalized;
  },

  /**
   * Clears any persistent backend URL override and re-detects the backend URL.
   * Also updates the currently cached Axios instance.
   */
  async clearBackendUrlOverride(): Promise<string> {
    try {
      localStorage.removeItem(STORAGE_KEY_BACKEND_URL_OVERRIDE);
    } catch {
      // Ignore
    }
    backendUrlCache = null;
    cacheTimestamp = 0;
    const resolved = await getBackendUrl();
    if (httpInstance) {
      httpInstance.defaults.baseURL = resolved;
    }
    return resolved;
  },

  async getPublicEndpoints(): Promise<string[]> {
    return await getPublicEndpoints();
  },

  async refreshPublicEndpoints(): Promise<string[]> {
    publicEndpointsCache = [];
    publicEndpointsTimestamp = 0;
    return await getPublicEndpoints();
  },
  
  // For backward compatibility with existing code
  create(config: AxiosRequestConfig) {
    return axios.create(config);
  }
};

// Initialize the HTTP instance when the module is loaded
getHttpInstance().catch(console.error);
