import { buildBriefing } from "../lib/copy";

interface BriefingProps {
  actNowCount: number;
  watchCount: number;
  unavailableCount: number;
}

export function Briefing({ actNowCount, watchCount, unavailableCount }: BriefingProps) {
  return (
    <p className="text-[26px] leading-snug font-bold tracking-tight text-ink sm:text-[30px]">
      {buildBriefing(actNowCount, watchCount, unavailableCount)}
    </p>
  );
}
