import { Link } from "react-router-dom";
import type { CreatorRosterEntry } from "../lib/types";
import { formatFollowers, getInitials } from "../lib/copy";

interface TopCreatorsListProps {
  creators: CreatorRosterEntry[];
}

// Deterministic string -> color, so the same creator always gets the same
// avatar color across a session/reload rather than a random one on every
// render. Purely decorative (carries no status meaning) — strictly the
// site's coral/violet palette (index.css), not an arbitrary rainbow.
const AVATAR_COLORS = ["#7670f2", "#fc896d", "#c9c6ff", "#fdb19b", "#9b96f8", "#fbb2c6"];

function avatarColor(handle: string): string {
  let hash = 0;
  for (let i = 0; i < handle.length; i++) hash = (hash * 31 + handle.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

// Top 5 creators by needs_attention_count — the same ranking the full
// Creator portfolio page sorts by (routes.py's get_creators), just capped
// to a home-screen-sized highlight. Real counts only; no post content
// duplicated here since that already lives in the triage sections below.
export function TopCreatorsList({ creators }: TopCreatorsListProps) {
  const ranked = creators.filter((c) => c.needs_attention_count > 0).slice(0, 5);

  if (ranked.length === 0) {
    return <p className="text-sm text-ink-muted">No creators need attention right now.</p>;
  }

  return (
    <ul className="divide-y divide-line">
      {ranked.map((creator) => (
        <li key={creator.id}>
          <Link
            to={`/creators/${creator.id}`}
            className="flex items-center gap-3 py-3 transition-colors hover:bg-black/[0.02] first:pt-0 last:pb-0"
          >
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[12px] font-medium text-white"
              style={{ backgroundColor: avatarColor(creator.handle) }}
            >
              {getInitials(creator.handle)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-ink">@{creator.handle}</p>
              <p className="mt-0.5 text-xs text-ink-muted">{formatFollowers(creator.followers)}</p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5 text-xs font-medium">
              {creator.taking_off_count > 0 && (
                <span className="rounded-full bg-taking-off-soft px-2 py-0.5 text-taking-off">
                  {creator.taking_off_count}
                </span>
              )}
              {creator.worth_watching_count > 0 && (
                <span className="rounded-full bg-watching-soft px-2 py-0.5 text-watching">
                  {creator.worth_watching_count}
                </span>
              )}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
