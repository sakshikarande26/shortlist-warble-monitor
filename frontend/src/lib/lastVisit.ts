// Tracks the real wall-clock time when Home last loaded successfully in
// this browser. The backend decides what changed inside that window; this
// value only tells it which window to use. If the marker is missing or
// malformed, the API falls back to its own six-hour history window.
const STORAGE_KEY = "warble-monitor:last-seen-at";

export function getLastSeenAt(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    const value = Date.parse(raw);
    return Number.isFinite(value) ? raw : null;
  } catch {
    return null;
  }
}

export function setLastSeenAt(timestamp: string = new Date().toISOString()): void {
  try {
    localStorage.setItem(STORAGE_KEY, timestamp);
  } catch {
    // A blocked storage write should not blank the dashboard.
  }
}
