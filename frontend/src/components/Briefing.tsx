import { useEffect, useState } from "react";
import { getAgentHeadline } from "../lib/api";
import { buildBriefing } from "../lib/copy";

interface BriefingProps {
  actNowCount: number;
  watchCount: number;
  unavailableCount: number;
}

// The page's top line. The deterministic sentence (built from real counts)
// renders immediately and is always correct; a model-written headline
// replaces it if one arrives, in its own non-blocking call. So the page is
// never waiting on a model, and never blank if one isn't available — the
// LLM makes this sharper, it isn't load-bearing.
export function Briefing({ actNowCount, watchCount, unavailableCount }: BriefingProps) {
  const [headline, setHeadline] = useState<string | null>(null);
  const summary = buildBriefing(actNowCount, watchCount, unavailableCount);

  useEffect(() => {
    let cancelled = false;
    getAgentHeadline()
      .then((response) => {
        if (!cancelled) setHeadline(response.headline);
      })
      .catch(() => {
        // Best-effort flourish: the deterministic line stands on its own.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <p className="text-[26px] leading-snug font-bold tracking-tight text-ink sm:text-[30px]">
        {headline ?? summary}
      </p>
      {headline && <p className="mt-1 text-sm text-ink-muted">{summary}</p>}
    </div>
  );
}
