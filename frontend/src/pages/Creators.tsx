import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getCreators } from "../lib/api";
import type { CreatorsResponse } from "../lib/types";
import { formatFollowers, getInitials, statusLabel } from "../lib/copy";
import { SkeletonCard, SkeletonLine } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";
import { Surface } from "../components/ui/Surface";
import { StatusPill } from "../components/ui/StatusPill";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: CreatorsResponse };

export function Creators() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    getCreators()
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load creators.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[26px] leading-snug font-medium tracking-tight text-ink sm:text-[30px]">
          Creators
        </p>
        {state.status === "ready" && (
          <p className="mt-1 text-sm text-ink-muted">
            {state.data.creators.length} creator{state.data.creators.length === 1 ? "" : "s"} in the
            program.
          </p>
        )}
      </div>

      {state.status === "loading" && <CreatorsSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={load} />}
      {state.status === "ready" && <CreatorsList data={state.data} />}
    </div>
  );
}

function CreatorsList({ data }: { data: CreatorsResponse }) {
  if (data.creators.length === 0) {
    return (
      <EmptyState
        title="No creators tracked yet"
        message="Once creators are enrolled in the program, they'll show up here."
      />
    );
  }

  return (
    <Surface className="divide-y divide-line">
      {data.creators.map((creator) => (
        <Link
          key={creator.id}
          to={`/creators/${creator.id}`}
          className="flex items-center gap-4 px-4 py-4 transition-colors hover:bg-black/[0.02] sm:px-6"
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-sm font-medium text-ink">
            {getInitials(creator.handle)}
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-medium text-ink">@{creator.handle}</span>
              {creator.needs_attention_count > 0 && (
                <StatusPill label={`${creator.needs_attention_count} needing attention`} />
              )}
            </div>
            <p className="mt-0.5 text-sm text-ink-muted">
              {formatFollowers(creator.followers)} · {creator.active_post_count} active post
              {creator.active_post_count === 1 ? "" : "s"}
            </p>
            {creator.strongest_post ? (
              <p className="mt-1 truncate text-sm text-ink">
                Strongest: {creator.strongest_post.caption ?? "Untitled post"} —{" "}
                {statusLabel(creator.strongest_post.state, false)}
              </p>
            ) : (
              <p className="mt-1 text-sm text-ink-muted">No active posts right now</p>
            )}
          </div>
        </Link>
      ))}
    </Surface>
  );
}

function CreatorsSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonLine width="w-1/3" />
      <SkeletonCard />
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}
