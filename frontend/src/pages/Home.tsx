import { useCallback, useEffect, useState } from "react";
import { ApiError, getHome } from "../lib/api";
import type { HomeResponse } from "../lib/types";
import { Briefing } from "../components/Briefing";
import { TriageSection } from "../components/TriageSection";
import { SkeletonLine, SkeletonCard } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";
import { StatStrip } from "../components/ui/StatStrip";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: HomeResponse };

export function Home() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    getHome()
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load the briefing.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      {state.status === "loading" && <HomeSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={load} />}
      {state.status === "ready" && <HomeContent data={state.data} />}
    </>
  );
}

// Home is triage only: what's taking off, and what's worth watching
// closely. Both lists arrive already ranked and capped by the backend's
// comparative-to-creator ranking — this page just renders what it's given,
// it doesn't re-derive groupings from state client-side (that was the old
// bug: a section's header and its cards' labels could disagree).
function HomeContent({ data }: { data: HomeResponse }) {
  const { act_now, watch_closely, total_posts, unavailable_count, current_sim_hours } = data;

  if (total_posts === 0) {
    return (
      <EmptyState
        title="No posts tracked yet"
        message="Once the collector discovers creator posts, they'll show up here."
      />
    );
  }

  if (act_now.length === 0 && watch_closely.length === 0) {
    return (
      <EmptyState
        title="Nothing needs triage right now"
        message="Nothing is outperforming what's normal for its creator at the moment. Browse everything being tracked in Creators."
        action={{ label: "Browse creators", to: "/creators" }}
      />
    );
  }

  return (
    <div className="space-y-8">
      <Briefing
        actNowCount={act_now.length}
        watchCount={watch_closely.length}
        unavailableCount={unavailable_count}
      />
      <StatStrip
        cells={[
          { label: "Act now", value: String(act_now.length) },
          { label: "Watching", value: String(watch_closely.length) },
          { label: "Unavailable", value: String(unavailable_count) },
        ]}
      />
      <TriageSection
        title="Act now"
        emptyMessage="Nothing is taking off right now"
        posts={act_now}
        currentSimHours={current_sim_hours}
      />
      <TriageSection
        title="Watch closely"
        emptyMessage="Nothing worth watching closely right now"
        posts={watch_closely}
        currentSimHours={current_sim_hours}
      />
    </div>
  );
}

function HomeSkeleton() {
  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <SkeletonLine width="w-5/6" />
        <SkeletonLine width="w-2/3" />
      </div>
      <div className="space-y-3">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  );
}
