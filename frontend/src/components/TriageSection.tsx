import type { ReactNode } from "react";
import type { HomePost } from "../lib/types";
import { PostCard } from "./PostCard";
import { EmptyState } from "./states/EmptyState";
import { Surface } from "./ui/Surface";

interface TriageSectionProps {
  title: string;
  emptyMessage: string;
  emptyDetail?: string;
  emptyExtra?: ReactNode;
  posts: HomePost[];
  currentSimHours: number | null;
}

// Posts arrive already selected and ordered by the backend — "Act now" is
// confirmed BREAKOUT posts plus top comparative movers, "Watch closely" is
// the next tier, ranked by how much each post is outperforming what's
// normal for its own creator (not by absolute state). This component just
// renders the list it's given.
export function TriageSection({
  title,
  emptyMessage,
  emptyDetail,
  emptyExtra,
  posts,
  currentSimHours,
}: TriageSectionProps) {
  return (
    <section>
      <h2 className="mb-3 text-[15px] font-medium text-ink">{title}</h2>
      {posts.length === 0 ? (
        <div className="space-y-3">
          <EmptyState title={emptyMessage} message={emptyDetail ?? "Nothing here right now."} />
          {emptyExtra}
        </div>
      ) : (
        <Surface className="divide-y divide-line">
          {posts.map((post) => (
            <PostCard key={post.post_id} post={post} currentSimHours={currentSimHours} />
          ))}
        </Surface>
      )}
    </section>
  );
}
