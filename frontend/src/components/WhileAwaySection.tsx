import { Link } from "react-router-dom";
import type { HomeResponse, HomeStateTransition } from "../lib/types";
import { getInitials, performanceStatement } from "../lib/copy";
import { StatusPill } from "./ui/StatusPill";

interface WhileAwaySectionProps {
  changes: HomeStateTransition[];
  windowType: HomeResponse["window_type"];
}

function sectionTitle(windowType: HomeResponse["window_type"]): string {
  return windowType === "since_last_visit" ? "Since your last visit" : "What changed in the last 6 hours";
}

// A distinct, warm-toned callout for state transitions inside the
// backend-selected briefing window. The title comes from the API window
// type, so first opens and repeat visits stay honest.
export function WhileAwaySection({ changes, windowType }: WhileAwaySectionProps) {
  if (changes.length === 0) return null;

  return (
    <section>
      <h2 className="mb-3 text-[15px] font-medium text-ink">{sectionTitle(windowType)}</h2>
      <div className="divide-y divide-taking-off/15 overflow-hidden rounded-xl border border-taking-off/25 bg-taking-off-soft">
        {changes.map((change) => (
          <Link
            key={`${change.post.post_id}-${change.changed_sim_hours}`}
            to={`/posts/${change.post.post_id}`}
            className="flex items-center gap-4 px-4 py-4 transition-colors hover:bg-black/[0.02] sm:px-6"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-sm font-medium text-ink">
              {getInitials(change.post.creator_handle)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-ink">@{change.post.creator_handle}</span>
                <StatusPill label={change.to_status_label} />
              </div>
              {change.post.caption && <p className="mt-0.5 truncate text-sm text-ink-muted">{change.post.caption}</p>}
              <p className="mt-1 text-sm text-ink">{performanceStatement(change.post)}</p>
              <p className="mt-0.5 text-xs text-ink-muted">
                {change.from_status_label} -&gt; {change.to_status_label}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
