import { Link } from "react-router-dom";
import { getPostsBoard } from "../lib/api";
import type { HomePost, PostsBoardResponse } from "../lib/types";
import { useCachedResource } from "../lib/dataCache";
import { formatRelativeSimTime, gainColumn, getInitials, paceColumn } from "../lib/copy";
import { Sparkline } from "../components/Sparkline";
import { SkeletonCard, SkeletonLine } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";
import { Surface } from "../components/ui/Surface";
import { StatusPill, statusTextColorClass } from "../components/ui/StatusPill";

// The full scoreboard: every active post, ranked by current momentum —
// highest first, never by lifetime views (the backend's _pace_sort_key
// already enforces that; this page just renders what it's given, same
// discipline as Home's triage sections). Home only ever shows a capped
// set of highlights; this is the complete working set behind it.
export function PostsBoard() {
  const { state, refresh } = useCachedResource<PostsBoardResponse>(
    "posts-board",
    getPostsBoard,
    "Couldn't load the board.",
  );

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[26px] leading-snug font-bold tracking-tight text-ink sm:text-[30px]">
          Track program posts
        </p>
        {state.status === "ready" && (
          <p className="mt-1 text-sm text-ink-muted">Active posts ranked from highest to lowest momentum.</p>
        )}
      </div>

      {state.status === "loading" && <BoardSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={refresh} />}
      {state.status === "ready" &&
        (state.data.posts.length === 0 ? (
          <EmptyState
            title="No posts tracked yet"
            message="Once the collector discovers creator posts, they'll show up here."
          />
        ) : (
          <>
            <div className="hidden items-center gap-2 px-4 text-[11px] font-medium tracking-wider text-ink-muted uppercase sm:flex sm:px-6">
              <span className="w-5 shrink-0" />
              <span className="min-w-0 flex-1">Post</span>
              <span className="w-24 shrink-0 text-right">Gain</span>
              <span className="w-16 shrink-0 text-right">Pace</span>
              <span className="w-[88px] shrink-0" />
            </div>
            <Surface className="max-h-[70vh] divide-y divide-line overflow-y-auto">
              {state.data.posts.map((post, index) => (
                <PostsBoardRow
                  key={post.post_id}
                  post={post}
                  rank={index + 1}
                  currentSimHours={state.data.current_sim_hours}
                />
              ))}
            </Surface>
          </>
        ))}
    </div>
  );
}

// A row built for scanning a ranked list, not reading prose: identity on
// the left, "+X views" and "X× baseline" as their own columns (not folded
// into a sentence the way PostCard's does), a trend on the right. Either
// column reads "—" rather than "0" when there isn't enough history for a
// real number — never a fabricated zero.
function PostsBoardRow({
  post,
  rank,
  currentSimHours,
}: {
  post: HomePost;
  rank: number;
  currentSimHours: number | null;
}) {
  const gain = gainColumn(post.evidence);
  const pace = paceColumn(post.evidence);

  return (
    <Link
      to={`/posts/${post.post_id}`}
      className="flex items-center gap-2 px-4 py-3 transition-colors hover:bg-black/[0.02] sm:px-6"
    >
      <span className="w-5 shrink-0 text-right text-xs tabular-nums text-ink-muted">{rank}</span>

      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-sm font-medium text-ink">
        {getInitials(post.creator_handle)}
      </div>

      <div className="min-w-0 flex-1 px-3">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-ink">@{post.creator_handle}</span>
          <StatusPill label={post.status_label} />
        </div>
        {post.caption && <p className="mt-0.5 truncate text-xs text-ink-muted">"{post.caption}"</p>}
        <p className="mt-0.5 text-xs text-ink-muted sm:hidden">
          {gain ?? "—"} · {pace ?? "—"}
        </p>
      </div>

      <span className="hidden w-24 shrink-0 text-right text-sm tabular-nums text-ink sm:block">
        {gain ?? "—"}
      </span>
      <span className="hidden w-16 shrink-0 text-right text-sm font-medium tabular-nums text-ink sm:block">
        {pace ?? "—"}
      </span>

      <div className="hidden w-[88px] shrink-0 items-center justify-end sm:flex">
        {post.sparkline.length > 1 ? (
          <div className={statusTextColorClass(post.status_label)}>
            <Sparkline values={post.sparkline} />
          </div>
        ) : (
          <span className="text-xs text-ink-muted">{formatRelativeSimTime(post.latest_sim_hours, currentSimHours, post.latest_metrics_at)}</span>
        )}
      </div>
    </Link>
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
