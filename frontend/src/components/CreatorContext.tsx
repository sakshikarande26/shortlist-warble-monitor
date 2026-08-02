import { Link } from "react-router-dom";
import type { CreatorContext as CreatorContextType } from "../lib/types";
import { formatFollowers, getInitials } from "../lib/copy";
import { Surface } from "./ui/Surface";

export function CreatorContext({ creator }: { creator: CreatorContextType }) {
  return (
    <Surface className="p-4">
      <Link to={`/creators/${creator.id}`} className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-sm font-medium text-ink">
          {getInitials(creator.handle)}
        </div>
        <div>
          <p className="text-sm font-medium text-ink">@{creator.handle}</p>
          <p className="text-xs text-ink-muted">
            {formatFollowers(creator.followers)}
            {creator.category && ` · ${creator.category}`}
          </p>
        </div>
      </Link>
    </Surface>
  );
}
