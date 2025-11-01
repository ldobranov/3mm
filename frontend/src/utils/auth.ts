import axios from 'axios';

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
let activityHandlerBound = false;
let refreshing = false;

export async function refreshToken(): Promise<boolean> {
  const token = getToken();
  if (!token) return false;
  try {
    const res = await axios.post(`${import.meta.env.VITE_API_BASE_URL}/api/user/refresh`, {}, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const newToken = res.data?.token;
    if (newToken) {
      setToken(newToken);
      scheduleRefresh();
      return true;
    }
  } catch {
    // ignore
  }
  return false;
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
  refreshTimer = window.setTimeout(async () => {
    if (refreshing) return;
    refreshing = true;
    const ok = await refreshToken();
    refreshing = false;
    if (!ok) {
      alert('Your session has expired. Please log in again.');
      clearAuth();
      window.location.replace('/user/login');
    }
  }, ms);
}

function onActivity() {
  scheduleRefresh();
}

export function initAuthLifecycle() {
  if (!activityHandlerBound) {
    activityHandlerBound = true;
    ['mousemove', 'keydown', 'click', 'visibilitychange'].forEach((evt) =>
      window.addEventListener(evt, onActivity, { passive: true })
    );
  }
  scheduleRefresh();
}

export function stopAuthLifecycle() {
  if (refreshTimer) window.clearTimeout(refreshTimer);
  ['mousemove', 'keydown', 'click', 'visibilitychange'].forEach((evt) =>
    window.removeEventListener(evt, onActivity)
  );
  activityHandlerBound = false;
}
