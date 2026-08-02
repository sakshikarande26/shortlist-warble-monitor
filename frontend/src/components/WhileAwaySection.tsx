import { Link } from "react-router-dom";
import type { HomePost } from "../lib/types";
import { getInitials, performanceStatement } from "../lib/copy";
import { StatusPill } from "./ui/StatusPill";

interface WhileAwaySectionProps {
  posts: HomePost[];
}

// A distinct, warm-toned callout for posts that took off since the
// marketer's last visit — pulled out from the regular "Act now" list
// (where they still also appear) so the ones that happened specifically
// while nobody was looking stand out, without framing it as something
// missed.
export function WhileAwaySection({ posts }: WhileAwaySectionProps) {
  if (posts.length === 0) return null;

  return (
    <section>
      <h2 className="mb-3 text-[15px] font-medium text-ink">While you were away</h2>
      <div className="divide-y divide-taking-off/15 overflow-hidden rounded-xl border border-taking-off/25 bg-taking-off-soft">
        {posts.map((post) => (
          <Link
            key={post.post_id}
            to={`/posts/${post.post_id}`}
            className="flex items-center gap-4 px-4 py-4 transition-colors hover:bg-black/[0.02] sm:px-6"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-sm font-medium text-ink">
              {getInitials(post.creator_handle)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-ink">@{post.creator_handle}</span>
                <StatusPill label={post.status_label} />
              </div>
              {post.caption && <p className="mt-0.5 truncate text-sm text-ink-muted">{post.caption}</p>}
              <p className="mt-1 text-sm text-ink">{performanceStatement(post)}</p>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
