import { Link } from "react-router-dom";
import type { HomePost } from "../lib/types";
import { formatRelativeSimTime, getInitials, isStale, performanceStatement } from "../lib/copy";
import { Sparkline } from "./Sparkline";
import { StatusPill, statusTextColorClass } from "./ui/StatusPill";

interface PostCardProps {
  post: HomePost;
  currentSimHours: number | null;
}

// A list row, not a floating card — hairline dividers between rows (from
// the parent's divide-y) carry the separation, not per-row borders/shadows.
export function PostCard({ post, currentSimHours }: PostCardProps) {
  const stale = isStale(post.latest_sim_hours, currentSimHours);

  return (
    <Link
      to={`/posts/${post.post_id}`}
      className="group flex items-center gap-4 px-4 py-4 transition-colors hover:bg-black/[0.02] sm:px-6"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-sm font-medium text-ink">
        {getInitials(post.creator_handle)}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-ink">@{post.creator_handle}</span>
          <StatusPill label={post.status_label} />
        </div>
        {post.caption && <p className="mt-0.5 truncate text-sm text-ink-muted">{post.caption}</p>}
        <p className="mt-1 text-sm text-ink">{performanceStatement(post)}</p>
        <p className="mt-1 text-xs text-ink-muted">
          {formatRelativeSimTime(post.latest_sim_hours, currentSimHours)}
          {stale && <span className="ml-1 text-ink">· hasn't refreshed in a while</span>}
        </p>
      </div>

      <div className={`hidden shrink-0 transition-opacity opacity-70 group-hover:opacity-100 sm:block ${statusTextColorClass(post.status_label)}`}>
        <Sparkline values={post.sparkline} />
      </div>
    </Link>
  );
}
