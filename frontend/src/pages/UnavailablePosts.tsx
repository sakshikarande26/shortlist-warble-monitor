import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getHome } from "../lib/api";
import type { HomeResponse } from "../lib/types";
import { formatRelativeSimTime, formatViews, getInitials } from "../lib/copy";
import type { LoadState } from "../lib/loadState";
import { SkeletonCard, SkeletonLine } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";
import { Surface } from "../components/ui/Surface";

export function UnavailablePosts() {
  const [state, setState] = useState<LoadState<HomeResponse>>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    getHome()
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load these posts.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[26px] leading-snug font-medium tracking-tight text-ink sm:text-[30px]">
          No longer available
        </p>
        <p className="mt-1 text-sm text-ink-muted">
          Posts that have come down. Their history is preserved, their numbers are frozen where they
          stopped.
        </p>
      </div>

      {state.status === "loading" && (
        <div className="space-y-3">
          <SkeletonLine width="w-1/3" />
          <SkeletonCard />
        </div>
      )}
      {state.status === "error" && <ErrorState message={state.message} onRetry={load} />}
      {state.status === "ready" &&
        (state.data.unavailable_posts.length === 0 ? (
          <EmptyState
            title="Nothing has come down"
            message="Every post being tracked is still live."
          />
        ) : (
          <Surface className="divide-y divide-line">
            {state.data.unavailable_posts.map((post) => (
              <Link
                key={post.post_id}
                to={`/posts/${post.post_id}`}
                className="flex items-center gap-4 px-4 py-4 transition-colors hover:bg-black/[0.02] sm:px-6"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-sm font-medium text-ink-muted">
                  {getInitials(post.creator_handle)}
                </div>
                <div className="min-w-0 flex-1">
                  <span className="truncate text-sm font-medium text-ink">@{post.creator_handle}</span>
                  {post.caption && (
                    <p className="mt-0.5 truncate text-sm text-ink-muted">"{post.caption}"</p>
                  )}
                  <p className="mt-1 text-sm text-ink-muted">
                    Last seen at {formatViews(post.views)} views ·{" "}
                    {formatRelativeSimTime(post.latest_sim_hours, state.data.current_sim_hours)}
                  </p>
                </div>
              </Link>
            ))}
          </Surface>
        ))}
    </div>
  );
}
