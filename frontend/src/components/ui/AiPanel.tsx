import { useSelection } from "../../lib/selection";
import { explainEvidence, statusLabel, suggestedActions } from "../../lib/copy";
import type { PostDetail } from "../../lib/types";
import { StatusPill } from "./StatusPill";

// Persistent right rail: context about whichever post is currently open in
// the center column. The interpretation and considerations are the same
// deterministic-evidence logic as before (lib/copy.ts's explainEvidence /
// suggestedActions) — just relocated here so every post detail view, from
// Home or from a creator's page, gets the same panel without duplicating
// the section in the center column too.
export function AiPanel() {
  const { activePost } = useSelection();

  return (
    <aside className="flex w-[340px] shrink-0 flex-col border-l border-line px-6 py-10">
      <p className="mb-6 text-[13px] font-medium tracking-wide text-ink-muted uppercase">Notes</p>
      {activePost ? <AiPanelContent post={activePost} /> : <AiPanelPlaceholder />}
    </aside>
  );
}

function AiPanelPlaceholder() {
  return (
    <p className="text-sm text-ink-muted">
      Select a post to see what's happening and what might be worth doing about it.
    </p>
  );
}

function AiPanelContent({ post }: { post: PostDetail }) {
  const label = statusLabel(post.state, post.is_gone);
  const actions = suggestedActions(post.state, post.is_gone);

  return (
    <div className="space-y-8">
      <div>
        <StatusPill label={label} />
        <p className="mt-3 text-sm font-medium text-ink">@{post.creator.handle}</p>
        {post.caption && <p className="mt-1 line-clamp-2 text-sm text-ink-muted">"{post.caption}"</p>}
      </div>

      <div>
        <h3 className="mb-2 text-[13px] font-medium text-ink">What's happening</h3>
        <p className="text-sm text-ink-muted">{explainEvidence(post)}</p>
      </div>

      <div>
        <h3 className="mb-2 text-[13px] font-medium text-ink">Worth considering</h3>
        <ul className="space-y-2">
          {actions.map((action) => (
            <li key={action} className="flex gap-2 text-sm text-ink-muted">
              <span>·</span>
              <span>{action}</span>
            </li>
          ))}
        </ul>
      </div>

      <p className="text-xs text-ink-muted/70">
        Deterministic notes for now — a generated brief will take over here soon.
      </p>
    </div>
  );
}
