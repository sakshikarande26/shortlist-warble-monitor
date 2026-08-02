import { Link } from "react-router-dom";
import type { CreatorPostSummary } from "../lib/types";
import { formatRelativeSimTime, isStale, performanceStatement, statusLabel } from "../lib/copy";
import { Sparkline } from "./Sparkline";
import { StatusPill } from "./ui/StatusPill";

interface CreatorPostRowProps {
  post: CreatorPostSummary;
  currentSimHours: number | null;
}

// A row within a creator's post list — same visual language as PostCard's
// rows, minus the creator avatar/handle (redundant here, since every row
// on this page already belongs to the one creator being viewed).
export function CreatorPostRow({ post, currentSimHours }: CreatorPostRowProps) {
  const label = statusLabel(post.state, post.is_gone);
  const stale = isStale(post.latest_sim_hours, currentSimHours);

  return (
    <Link
      to={`/posts/${post.post_id}`}
      className="group flex items-center gap-4 px-4 py-4 transition-colors hover:bg-black/[0.02] sm:px-6"
    >
      <div className="min-w-0 flex-1">
        <StatusPill label={label} />
        {post.caption && <p className="mt-1.5 truncate text-sm text-ink">{post.caption}</p>}
        <p className="mt-1 text-sm text-ink-muted">{performanceStatement(post)}</p>
        <p className="mt-1 text-xs text-ink-muted">
          {formatRelativeSimTime(post.latest_sim_hours, currentSimHours)}
          {stale && <span className="ml-1 text-ink">· hasn't refreshed in a while</span>}
        </p>
      </div>

      <div className="hidden shrink-0 text-ink-muted transition-colors group-hover:text-ink sm:block">
        <Sparkline values={post.sparkline} />
      </div>
    </Link>
  );
}
