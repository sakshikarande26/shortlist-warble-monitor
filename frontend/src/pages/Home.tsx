import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getBreakoutLog, getHome, getStatus } from "../lib/api";
import type { BreakoutLogResponse, HomeResponse, SystemStatus } from "../lib/types";
import type { LoadState } from "../lib/loadState";
import { Briefing } from "../components/Briefing";
import { TriageSection } from "../components/TriageSection";
import { WhileAwaySection } from "../components/WhileAwaySection";
import { ProgramPulse } from "../components/ProgramPulse";
import { SpotlightPostCard } from "../components/SpotlightPostCard";
import { PostCard } from "../components/PostCard";
import { Surface } from "../components/ui/Surface";
import { SkeletonLine, SkeletonCard } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";
import { getLastSeenAt, setLastSeenAt } from "../lib/lastVisit";
import { formatRelativeSimTime, getInitials } from "../lib/copy";

// How many "Removed" rows to preview on Home — the full list lives on
// /unavailable. Matches the backend's own section cap for the other
// Momentum Board groups (routes.py's _SECTION_CAP).
const REMOVED_PREVIEW_CAP = 5;

// Home is the Momentum Board screen — it needs three endpoints at once
// (home + status + the breakout log, for Program Pulse's Weekly view) so
// its "ready" data is all three rather than one response.
interface HomeData {
  home: HomeResponse;
  status: SystemStatus;
  breakouts: BreakoutLogResponse;
}

export function Home() {
  const [state, setState] = useState<LoadState<HomeData>>({ status: "loading" });

  const load = useCallback(() => {
    const lastSeenAt = getLastSeenAt();
    setState({ status: "loading" });
    Promise.all([getHome(lastSeenAt), getStatus(), getBreakoutLog()])
      .then(([home, status, breakouts]) => {
        setState({ status: "ready", data: { home, status, breakouts } });
        setLastSeenAt();
      })
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
      {state.status === "ready" && (
        <HomeContent data={state.data.home} status={state.data.status} breakouts={state.data.breakouts} />
      )}
    </>
  );
}

// Home is triage only: what's taking off, and what's worth watching
// closely. Both lists arrive already ranked and capped by the backend's
// comparative-to-creator ranking — this page just renders what it's given,
// it doesn't re-derive groupings from state client-side (that was the old
// bug: a section's header and its cards' labels could disagree).
function HomeContent({
  data,
  status,
  breakouts,
}: {
  data: HomeResponse;
  status: SystemStatus;
  breakouts: BreakoutLogResponse;
}) {
  const { act_now, watch_closely, new_posts, unavailable_posts, total_posts, unavailable_count, current_sim_hours } =
    data;

  if (total_posts === 0) {
    return (
      <EmptyState
        title="No posts tracked yet"
        message="Once the collector discovers creator posts, they'll show up here."
      />
    );
  }

  if (
    act_now.length === 0 &&
    watch_closely.length === 0 &&
    new_posts.length === 0 &&
    unavailable_count === 0
  ) {
    return (
      <EmptyState
        title="Nothing needs triage right now"
        message="Nothing is outperforming what's normal for its creator at the moment. Browse everything being tracked in Creators."
        action={{ label: "Browse creators", to: "/creators" }}
      />
    );
  }

  const removedPreview = unavailable_posts.slice(0, REMOVED_PREVIEW_CAP);

  return (
    <div className="space-y-8">
      <ProgramPulse
        program={{
          postsCount: total_posts,
          needsAttentionCount: act_now.length + watch_closely.length,
          breakoutsCount: breakouts.entries.length,
        }}
        weekly={{
          alertsReceivedCount: status.alerts_sent,
          newCount: new_posts.length,
          removedCount: unavailable_count,
        }}
      />

      <Briefing
        actNowCount={act_now.length}
        watchCount={watch_closely.length}
        unavailableCount={unavailable_count}
      />
      <WhileAwaySection
        changes={data.recent_changes ?? []}
        windowType={data.window_type ?? "last_6_hours"}
      />

      <section>
        <h2 className="mb-3 text-[15px] font-medium text-ink">Act now</h2>
        {act_now.length > 0 ? (
          <div className="space-y-3">
            {/* The strongest current breakout gets the spotlight
                treatment — only ever shown when it's a genuine breakout,
                never for a "Worth watching" post, and never duplicated:
                the rest of act_now (if any) lists separately below it. */}
            <SpotlightPostCard post={act_now[0]} currentSimHours={current_sim_hours} />
            {act_now.length > 1 && (
              <Surface className="divide-y divide-line">
                {act_now.slice(1).map((post) => (
                  <PostCard key={post.post_id} post={post} currentSimHours={current_sim_hours} />
                ))}
              </Surface>
            )}
          </div>
        ) : (
          <div className="lifted-glass-card rounded-2xl p-5 sm:p-6">
            <p className="text-[15px] font-semibold text-ink">All quiet on the breakout front</p>
            <p className="mt-1 text-sm text-ink-muted">
              Nothing is taking off right now, but we're still watching closely.
            </p>
            <LastBreakoutInsight status={status} currentSimHours={current_sim_hours} />
          </div>
        )}
      </section>
      <TriageSection
        title="Watch closely"
        emptyMessage="Nothing worth watching closely right now"
        posts={watch_closely}
        currentSimHours={current_sim_hours}
      />
      <TriageSection
        title="New"
        emptyMessage="Nothing new to review"
        emptyDetail="No recently discovered posts are still building their initial history."
        posts={new_posts}
        currentSimHours={current_sim_hours}
      />
      {unavailable_posts.length > 0 && (
        <TriageSection
          title="Removed"
          emptyMessage="Nothing removed"
          posts={removedPreview}
          currentSimHours={current_sim_hours}
        />
      )}
      {unavailable_posts.length > REMOVED_PREVIEW_CAP && (
        <Link
          to="/unavailable"
          className="block text-xs font-medium text-ink-muted transition-colors hover:text-accent"
        >
          View all {unavailable_posts.length} removed posts &rarr;
        </Link>
      )}
    </div>
  );
}

// When there's nothing to triage right now, surface the last real
// breakout instead of leaving a flat empty box — a genuine data point
// (from the Alert table), not a fabricated "nothing ever happens" message.
function LastBreakoutInsight({
  status,
  currentSimHours,
}: {
  status: SystemStatus;
  currentSimHours: number | null;
}) {
  if (!status.most_recent_alert) return null;
  const alert = status.most_recent_alert;
  return (
    <Link
      to={`/posts/${alert.post_id}`}
      className="mt-4 flex items-center gap-3 rounded-xl border border-line bg-black/[0.02] p-3 transition-colors hover:border-ink/20 hover:bg-white"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-sm font-semibold text-ink">
        {getInitials(alert.creator_handle)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-semibold tracking-wider text-ink-muted uppercase">
          Last confirmed breakout
        </p>
        <p className="mt-0.5 truncate text-sm text-ink">
          <span className="font-medium">@{alert.creator_handle}</span>
          {alert.caption && <span className="text-ink-muted">, "{alert.caption}"</span>}
        </p>
        <p className="mt-0.5 text-xs text-ink-muted">
          {formatRelativeSimTime(alert.sim_hours, currentSimHours)}
        </p>
      </div>
    </Link>
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
