import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, getCreatorDetail } from "../lib/api";
import type { CreatorDetailResponse } from "../lib/types";
import { formatFollowers, formatViews, getInitials } from "../lib/copy";
import { useSelection } from "../lib/selection";
import { CreatorPostRow } from "../components/CreatorPostRow";
import { SkeletonCard, SkeletonLine } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";
import { StatStrip } from "../components/ui/StatStrip";
import { Surface } from "../components/ui/Surface";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: CreatorDetailResponse };

export function CreatorDetail() {
  const { creatorId } = useParams<{ creatorId: string }>();
  const navigate = useNavigate();
  const { setActiveCreator } = useSelection();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(() => {
    if (!creatorId) return;
    setState({ status: "loading" });
    getCreatorDetail(creatorId)
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load this creator.";
        setState({ status: "error", message });
      });
  }, [creatorId]);

  useEffect(() => {
    load();
  }, [load]);

  // Publishes the loaded creator into the shared selection so the right
  // panel can answer questions about them. Clears on unmount.
  useEffect(() => {
    if (state.status === "ready") {
      setActiveCreator(state.data);
    }
    return () => setActiveCreator(null);
  }, [state, setActiveCreator]);

  return (
    <>
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="text-xs tracking-wide text-ink-muted transition-colors hover:text-ink"
      >
        ← Back
      </button>

      <div className="mt-6">
        {state.status === "loading" && <CreatorDetailSkeleton />}
        {state.status === "error" && <ErrorState message={state.message} onRetry={load} />}
        {state.status === "ready" && <CreatorDetailContent data={state.data} />}
      </div>
    </>
  );
}

function CreatorDetailContent({ data }: { data: CreatorDetailResponse }) {
  const { creator, active_posts, unavailable_posts, stats, current_sim_hours } = data;

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-base font-medium text-ink">
          {getInitials(creator.handle)}
        </div>
        <div>
          <p className="text-[22px] font-medium tracking-tight text-ink">@{creator.handle}</p>
          <p className="text-sm text-ink-muted">
            {formatFollowers(creator.followers)}
            {creator.category && ` · ${creator.category}`}
          </p>
        </div>
      </div>

      <StatStrip
        cells={[
          { label: "Posts tracked", value: String(stats.posts_tracked) },
          { label: "Took off", value: String(stats.posts_that_took_off) },
          { label: "Typical performance", value: formatViews(stats.typical_views), sub: "views per post" },
        ]}
      />

      <section>
        <h2 className="mb-3 text-[15px] font-medium text-ink">Active posts</h2>
        {active_posts.length === 0 ? (
          <EmptyState title="No active posts" message="This creator has no active posts being tracked." />
        ) : (
          <Surface className="divide-y divide-line">
            {active_posts.map((post) => (
              <CreatorPostRow key={post.post_id} post={post} currentSimHours={current_sim_hours} />
            ))}
          </Surface>
        )}
      </section>

      {unavailable_posts.length > 0 && (
        <section>
          <h2 className="mb-3 text-[15px] font-medium text-ink">Unavailable</h2>
          <p className="mb-3 text-sm text-ink-muted">
            No longer live, but their history is preserved below.
          </p>
          <Surface className="divide-y divide-line">
            {unavailable_posts.map((post) => (
              <CreatorPostRow key={post.post_id} post={post} currentSimHours={current_sim_hours} />
            ))}
          </Surface>
        </section>
      )}
    </div>
  );
}

function CreatorDetailSkeleton() {
  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <SkeletonLine width="w-40" />
        <SkeletonLine width="w-24" />
      </div>
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}
