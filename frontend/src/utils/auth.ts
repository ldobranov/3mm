import axios from 'axios';
import http from '@/utils/dynamic-http';

export function getToken(): string {
  return localStorage.getItem('authToken') || '';
}
export function setToken(t: string) {
  localStorage.setItem('authToken', t);
}
export function clearAuth() {
  localStorage.removeItem('authToken');
  localStorage.removeItem('role');
  localStorage.removeItem('username');
}

function decodeExp(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return typeof payload.exp === 'number' ? payload.exp : null;
  } catch {
    return null;
  }
}

let refreshTimer: number | null = null;
let foregroundHandlerBound = false;
let refreshing = false;

type RefreshResult = 'refreshed' | 'rejected' | 'unavailable';

async function refreshTokenResult(): Promise<RefreshResult> {
  const token = getToken();
  if (!token) return 'rejected';
  try {
    const backendUrl = await http.getCurrentBackendUrl();
    const res = await axios.post(`${backendUrl}/api/user/refresh`, {}, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const newToken = res.data?.token;
    if (newToken) {
      setToken(newToken);
      scheduleRefresh();
      return 'refreshed';
    }
    return 'rejected';
  } catch (error: any) {
    const status = error?.response?.status;
    return status === 401 || status === 403 ? 'rejected' : 'unavailable';
  }
}

export async function refreshToken(): Promise<boolean> {
  return (await refreshTokenResult()) === 'refreshed';
}

function expireBrowserSession() {
  alert('Your session has expired. Please log in again.');
  clearAuth();
  window.location.replace('/user/login');
}

function scheduleTemporaryRetry() {
  if (refreshTimer) window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(runScheduledRefresh, 30_000);
}

async function runScheduledRefresh() {
  if (refreshing) return;
  refreshing = true;
  const result = await refreshTokenResult();
  refreshing = false;
  if (result === 'rejected') {
    expireBrowserSession();
  } else if (result === 'unavailable') {
    // A deployment or short network interruption must not sign the user out.
    scheduleTemporaryRetry();
  }
}

export function scheduleRefresh() {
  if (refreshTimer) window.clearTimeout(refreshTimer);
  const token = getToken();
  const exp = decodeExp(token);
  if (!exp) return;
  const nowSec = Math.floor(Date.now() / 1000);
  const secondsToExp = exp - nowSec;
  // Refresh 2 minutes before expiry; minimum 10s
  const ms = Math.max((secondsToExp - 120) * 1000, 10_000);
  refreshTimer = window.setTimeout(runScheduledRefresh, ms);
}

async function onForeground() {
  if (document.visibilityState === 'hidden' || refreshing || !getToken()) return;
  const exp = decodeExp(getToken());
  const nowSec = Math.floor(Date.now() / 1000);
  if (exp !== null && exp - nowSec > 120) {
    scheduleRefresh();
    return;
  }
  await runScheduledRefresh();
}

export function initAuthLifecycle() {
  if (!foregroundHandlerBound) {
    foregroundHandlerBound = true;
    document.addEventListener('visibilitychange', onForeground, { passive: true });
    window.addEventListener('focus', onForeground, { passive: true });
  }
  scheduleRefresh();
}

export function stopAuthLifecycle() {
  if (refreshTimer) window.clearTimeout(refreshTimer);
  document.removeEventListener('visibilitychange', onForeground);
  window.removeEventListener('focus', onForeground);
  foregroundHandlerBound = false;
}
