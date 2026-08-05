import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";
import type { LoadState } from "./loadState";

// Client-side stale-while-revalidate cache.
//
// Every page used to refetch from scratch on mount, so navigating Home →
// Posts → Home meant three full round trips and three skeletons, even though
// the data was seconds old. Here a page renders its last known data
// immediately and refreshes underneath — the skeleton is now only for a
// genuinely cold screen, which is the one time it's telling the truth.
//
// Deliberately hand-rolled rather than pulling in React Query: this is one
// map, one in-flight table, and one hook, and a cache is easier to reason
// about when you can read all of it.

interface CacheEntry {
  data: unknown;
  storedAt: number;
}

const cache = new Map<string, CacheEntry>();
// Shared promises for identical concurrent requests, so two components
// mounting at once produce one network call rather than two.
const inflight = new Map<string, Promise<unknown>>();

// How long a cached entry is served without a background refresh. Matches
// the backend's own dataset cache TTL — refreshing faster than the server
// recomputes would just re-fetch an identical payload.
const DEFAULT_TTL_MS = 20_000;

// The collector writes a new round of samples every 15 minutes, but a
// dashboard left open should never be the last to know. Polling every minute
// keeps an idle tab current without being anywhere near the collector's own
// cadence. Refreshes happen underneath the data already on screen — no
// skeleton, no scroll jump — so a tab nobody is touching quietly stays true.
const AUTO_REFRESH_MS = 60_000;

export function invalidateCache(): void {
  cache.clear();
}

function fetchShared<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;

  const promise = fetcher()
    .then((data) => {
      cache.set(key, { data, storedAt: Date.now() });
      return data;
    })
    .finally(() => {
      inflight.delete(key);
    });

  inflight.set(key, promise);
  return promise;
}

interface CachedResource<T> {
  state: LoadState<T>;
  /** True while a background refresh is in flight over already-shown data —
   * for a quiet indicator, never a skeleton. */
  isRevalidating: boolean;
  /** Force a fetch regardless of freshness (the error-state retry button). */
  refresh: () => void;
}

export function useCachedResource<T>(
  key: string,
  fetcher: () => Promise<T>,
  fallbackMessage: string,
  ttlMs: number = DEFAULT_TTL_MS,
): CachedResource<T> {
  const cached = cache.get(key);
  const [state, setState] = useState<LoadState<T>>(
    cached ? { status: "ready", data: cached.data as T } : { status: "loading" },
  );
  const [isRevalidating, setIsRevalidating] = useState(false);

  // Keeps the latest fetcher without making it a dependency of the effect —
  // pages build their fetcher inline, so a new function identity every
  // render would otherwise refetch in a loop.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(
    (force: boolean) => {
      const entry = cache.get(key);
      const isFresh = entry !== undefined && Date.now() - entry.storedAt < ttlMs;

      if (entry) {
        setState({ status: "ready", data: entry.data as T });
        if (isFresh && !force) return;
        setIsRevalidating(true);
      } else {
        setState({ status: "loading" });
      }

      let cancelled = false;
      fetchShared(key, fetcherRef.current)
        .then((data) => {
          if (!cancelled) setState({ status: "ready", data: data as T });
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          // A failed background refresh must not blow away good data that's
          // already on screen — the error state is only for a cold load.
          if (cache.has(key)) return;
          setState({
            status: "error",
            message: error instanceof ApiError ? error.message : fallbackMessage,
          });
        })
        .finally(() => {
          if (!cancelled) setIsRevalidating(false);
        });

      return () => {
        cancelled = true;
      };
    },
    [key, ttlMs, fallbackMessage],
  );

  useEffect(() => load(false), [load]);

  // Poll while the tab is actually being looked at. A backgrounded tab is
  // skipped rather than burning requests nobody will read, and the
  // visibilitychange listener refreshes the moment it comes back — so
  // returning to a tab left open for an hour shows current data, not an
  // hour-old snapshot waiting for the next tick.
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden) load(true);
    }, AUTO_REFRESH_MS);

    const onVisible = () => {
      if (!document.hidden) load(true);
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load]);

  return { state, isRevalidating, refresh: () => load(true) };
}
