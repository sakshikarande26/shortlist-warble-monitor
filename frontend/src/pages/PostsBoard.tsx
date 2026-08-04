import { useCallback, useEffect, useState } from "react";
import { ApiError, getPostsBoard } from "../lib/api";
import type { PostsBoardResponse } from "../lib/types";
import type { LoadState } from "../lib/loadState";
import { PostCard } from "../components/PostCard";
import { SkeletonCard, SkeletonLine } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";
import { Surface } from "../components/ui/Surface";

// The full scoreboard: every active post, ranked by current momentum —
// highest first, never by lifetime views (the backend's _pace_sort_key
// already enforces that; this page just renders what it's given, same
// discipline as Home's triage sections). Home only ever shows a capped
// set of highlights; this is the complete working set behind it.
export function PostsBoard() {
  const [state, setState] = useState<LoadState<PostsBoardResponse>>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    getPostsBoard()
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load the board.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[26px] leading-snug font-bold tracking-tight text-ink sm:text-[30px]">
          Track program posts
        </p>
        {state.status === "ready" && (
          <p className="mt-1 text-sm text-ink-muted">
            {state.data.total_posts} post{state.data.total_posts === 1 ? "" : "s"} tracked, ranked by
            current momentum — highest first.
          </p>
        )}
      </div>

      {state.status === "loading" && <BoardSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={load} />}
      {state.status === "ready" &&
        (state.data.posts.length === 0 ? (
          <EmptyState
            title="No posts tracked yet"
            message="Once the collector discovers creator posts, they'll show up here."
          />
        ) : (
          <Surface className="max-h-[70vh] divide-y divide-line overflow-y-auto">
            {state.data.posts.map((post, index) => (
              <div key={post.post_id} className="flex items-center gap-2 pl-3">
                <span className="w-5 shrink-0 text-right text-xs tabular-nums text-ink-muted">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <PostCard post={post} currentSimHours={state.data.current_sim_hours} />
                </div>
              </div>
            ))}
          </Surface>
        ))}
    </div>
  );
}

function BoardSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonLine width="w-1/3" />
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}
