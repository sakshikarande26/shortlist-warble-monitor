// Tracks, client-side only, the sim_hours as of the marketer's last visit
// to Home — so a post that broke out since then can be called out
// specifically ("while you were away"), not just folded anonymously into
// the regular queue. No backend concept of "last visit" exists (no user
// accounts), so this is deliberately a local, best-effort marker: it
// resets if the user clears storage or opens a different browser, which
// is an acceptable trade-off for a nice-to-have highlight, not a source
// of truth for anything the product depends on.
const STORAGE_KEY = "warble-monitor:last-visit-sim-hours";

export function getLastVisitSimHours(): number | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw === null) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function setLastVisitSimHours(simHours: number): void {
  localStorage.setItem(STORAGE_KEY, String(simHours));
}
