import type { PostDetail } from "../lib/types";
import { formatRelativeSimTime, isStale, statusSummary } from "../lib/copy";
import { StatusPill } from "./ui/StatusPill";

interface StatusSummaryProps {
  detail: PostDetail;
}

export function StatusSummary({ detail }: StatusSummaryProps) {
  const latestSimHours = detail.trajectory.at(-1)?.sim_hours ?? null;
  const stale = isStale(latestSimHours, detail.current_sim_hours);

  return (
    <div>
      <StatusPill label={detail.status_label} />
      <p className="mt-3 text-[26px] leading-snug font-medium tracking-tight text-ink sm:text-[30px]">
        {statusSummary(detail)}
      </p>
      <p className="mt-2 text-sm text-ink-muted">
        {formatRelativeSimTime(latestSimHours, detail.current_sim_hours)}
        {stale && <span className="ml-1 text-ink">· hasn't refreshed in a while</span>}
      </p>
    </div>
  );
}
