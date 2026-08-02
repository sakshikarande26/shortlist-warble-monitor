import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, getPostDetail } from "../lib/api";
import type { PostDetail as PostDetailType } from "../lib/types";
import { formatPublishedAt } from "../lib/copy";
import { useSelection } from "../lib/selection";
import { StatusSummary } from "../components/StatusSummary";
import { GrowthChart } from "../components/GrowthChart";
import { CreatorContext } from "../components/CreatorContext";
import { SkeletonChart, SkeletonLine } from "../components/states/Skeleton";
import { ErrorState } from "../components/states/ErrorState";
import { Surface } from "../components/ui/Surface";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: PostDetailType };

export function PostDetail() {
  const { postId } = useParams<{ postId: string }>();
  const navigate = useNavigate();
  const { setActivePost } = useSelection();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(() => {
    if (!postId) return;
    setState({ status: "loading" });
    getPostDetail(postId)
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load this post.";
        setState({ status: "error", message });
      });
  }, [postId]);

  useEffect(() => {
    load();
  }, [load]);

  // Publishes the loaded post into the shared selection so the right-hand
  // panel (rendered by the persistent app shell, not by this page) can
  // show its interpretation and considerations. Clears on unmount, so
  // navigating away drops back to the panel's system-status view.
  useEffect(() => {
    if (state.status === "ready") {
      setActivePost(state.data);
    }
    return () => setActivePost(null);
  }, [state, setActivePost]);

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
        {state.status === "loading" && <DetailSkeleton />}
        {state.status === "error" && <ErrorState message={state.message} onRetry={load} />}
        {state.status === "ready" && <DetailContent detail={state.data} />}
      </div>
    </>
  );
}

function DetailContent({ detail }: { detail: PostDetailType }) {
  return (
    <div className="space-y-8">
      <StatusSummary detail={detail} />

      <div className="space-y-1">
        {detail.caption && <p className="text-sm text-ink-muted">"{detail.caption}"</p>}
        <p className="text-xs text-ink-muted">
          Published {formatPublishedAt(detail.published_at)} · {detail.platform}
        </p>
      </div>

      <Surface className="p-4 sm:p-6">
        <GrowthChart
          trajectory={detail.trajectory}
          isGone={detail.is_gone}
          goneSimHours={detail.gone_sim_hours}
          statusLabel={detail.status_label}
        />
      </Surface>

      <CreatorContext creator={detail.creator} />
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <SkeletonLine width="w-24" />
        <SkeletonLine width="w-4/5" />
      </div>
      <SkeletonChart />
    </div>
  );
}
