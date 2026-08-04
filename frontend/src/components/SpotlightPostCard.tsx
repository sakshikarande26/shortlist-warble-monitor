import { Link } from "react-router-dom";
import type { HomePost } from "../lib/types";
import { evidenceChips, formatRelativeSimTime, getInitials, performanceStatement } from "../lib/copy";
import { Sparkline } from "./Sparkline";
import { StatusPill, statusTextColorClass } from "./ui/StatusPill";

interface SpotlightPostCardProps {
  post: HomePost;
  currentSimHours: number | null;
}

// The one post a marketer should see before anything else: the most
// notable thing happening in the program right now (same post
// SystemStatus.most_notable_post already points to). A marketer opening
// Home needs, in order: who, what's happening, why it's real (the
// evidence, not just a status word), how fresh, and a trend shape — all
// in one glance, before they even scroll to the grouped board below.
export function SpotlightPostCard({ post, currentSimHours }: SpotlightPostCardProps) {
  const chips = evidenceChips(post.evidence);

  return (
    <Link
      to={`/posts/${post.post_id}`}
      className="group block overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-tint-breakout to-white transition-colors hover:border-taking-off/40"
    >
      <div className="flex items-start gap-4 p-5 sm:p-6">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white text-base font-semibold text-ink shadow-[0_1px_3px_rgb(0_0_0_/_10%)]">
          {getInitials(post.creator_handle)}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[10px] font-semibold tracking-wider text-taking-off uppercase">Spotlight</p>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <span className="truncate text-[15px] font-semibold text-ink">@{post.creator_handle}</span>
            <StatusPill label={post.status_label} />
          </div>
          {post.caption && <p className="mt-1 truncate text-sm text-ink-muted">"{post.caption}"</p>}
          <p className="mt-2 text-sm text-ink">{performanceStatement(post)}</p>

          {chips.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {chips.map((chip) => (
                <span
                  key={chip}
                  className="rounded-full border border-line bg-white/80 px-2.5 py-0.5 text-[11px] font-medium text-ink-muted"
                >
                  {chip}
                </span>
              ))}
            </div>
          )}

          <p className="mt-3 text-xs text-ink-muted">
            {formatRelativeSimTime(post.latest_sim_hours, currentSimHours)}
          </p>
        </div>

        {post.sparkline.length > 1 && (
          <div className={`hidden shrink-0 pt-1 sm:block ${statusTextColorClass(post.status_label)}`}>
            <Sparkline values={post.sparkline} width={120} height={44} />
          </div>
        )}
      </div>
    </Link>
  );
}
