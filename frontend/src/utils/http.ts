import axios from 'axios';
import { getToken, refreshToken, clearAuth } from '@/utils/auth';

const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL });

http.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers || {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});

let isRefreshing = false as boolean;
let queued: Array<(token: string | null) => void> = [];

http.interceptors.response.use(
  (res) => res,
  async (error) => {
    const status = error?.response?.status;
    const original = error.config;

    if ((status === 401 || status === 403) && !original._retry) {
      if (!isRefreshing) {
        isRefreshing = true;
        const ok = await refreshToken();
        isRefreshing = false;
        queued.forEach((cb) => cb(ok ? getToken() : null));
        queued = [];
        if (ok) {
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
      }

      return new Promise((resolve, reject) => {
        queued.push((newToken) => {
          if (newToken) {
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

    return Promise.reject(error);
  }
);

export default http;
