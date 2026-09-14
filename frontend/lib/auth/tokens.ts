/**
 * Where the device token and the current staff/guest token live on this device.
 * WS07 wraps this in Zustand stores with UI; the API client only needs these getters.
 * localStorage can be unavailable (private mode) — every access is guarded.
 */

const DEVICE_KEY = "renzy.device_token";
const SESSION_KEY = "renzy.session_token";

function read(key: string): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (typeof window === "undefined") return;
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* ignore: private mode or storage disabled */
  }
}

export const tokens = {
  device: (): string | null => read(DEVICE_KEY),
  setDevice: (value: string | null): void => write(DEVICE_KEY, value),
  /** Staff JWT or guest JWT, whichever is active on this device. */
  session: (): string | null => read(SESSION_KEY),
  setSession: (value: string | null): void => write(SESSION_KEY, value),
};
