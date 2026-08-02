import { useEffect, useState } from "react";
import { useSelection } from "../../lib/selection";
import {
  answerAlertStatus,
  answerBaselineComparison,
  answerNextSteps,
  answerRecentAlert,
  answerStrongestMomentum,
  answerWhatChanged,
  answerWhatChangedSinceLastCheck,
  answerWhichPostsNeedAttention,
  answerWhyStatus,
  evidenceChips,
  formatMonitoringProgress,
} from "../../lib/copy";
import { getHome, getStatus } from "../../lib/api";
import type { HomeResponse, PostDetail, SystemStatus } from "../../lib/types";
import { StatusPill } from "./StatusPill";

interface QuestionItem {
  id: string;
  label: string;
  answer: string;
  chips?: string[];
}

type IdleLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; systemStatus: SystemStatus; home: HomeResponse };

// The right rail is a teammate, not a chatbot: a fixed set of pre-built
// questions with deterministic, evidence-grounded answers (no LLM wired up
// yet — see lib/copy.ts). Two modes: nothing selected answers questions
// about the whole program; a post selected answers questions about it.
export function AiPanel() {
  const { activePost } = useSelection();
  const [idleState, setIdleState] = useState<IdleLoadState>({ status: "loading" });

  useEffect(() => {
    if (activePost) return;
    setIdleState({ status: "loading" });
    Promise.all([getStatus(), getHome()])
      .then(([systemStatus, home]) => setIdleState({ status: "ready", systemStatus, home }))
      .catch(() => setIdleState({ status: "error" }));
  }, [activePost]);

  return (
    <aside className="flex w-[340px] shrink-0 flex-col border-l border-line px-6 py-10">
      <p className="mb-1 text-[13px] font-medium tracking-wide text-ink-muted uppercase">Teammate</p>
      <p className="mb-6 text-xs text-ink-muted">
        {activePost ? "Ask about this post" : "Ask about your program"}
      </p>
      {activePost ? <SelectedPostPanel post={activePost} /> : <IdlePanel state={idleState} />}
    </aside>
  );
}

function IdlePanel({ state }: { state: IdleLoadState }) {
  if (state.status === "loading") return <PanelSkeleton />;
  if (state.status === "error") {
    return <p className="text-sm text-ink-muted">Couldn't load your program's status.</p>;
  }

  const { systemStatus, home } = state;
  const questions: QuestionItem[] = [
    {
      id: "changed",
      label: "What changed since the last check?",
      answer: answerWhatChangedSinceLastCheck(systemStatus),
    },
    {
      id: "attention",
      label: "Which posts need attention right now?",
      answer: answerWhichPostsNeedAttention(home),
    },
    {
      id: "strongest",
      label: "Which post has the strongest momentum?",
      answer: answerStrongestMomentum(home),
    },
    {
      id: "alert",
      label: "Was an alert sent recently?",
      answer: answerRecentAlert(systemStatus),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-ink">
          Watching {systemStatus.posts_tracked} post{systemStatus.posts_tracked === 1 ? "" : "s"} across
          your creator program.
        </p>
        {systemStatus.last_checked_sim_hours !== null && (
          <p className="mt-1 text-xs text-ink-muted">
            {formatMonitoringProgress(systemStatus.last_checked_sim_hours)} of monitoring
          </p>
        )}
      </div>

      <QuestionList questions={questions} />
    </div>
  );
}

function SelectedPostPanel({ post }: { post: PostDetail }) {
  const chips = evidenceChips(post.evidence);
  const questions: QuestionItem[] = [
    {
      id: "why",
      label: `Why is this ${post.status_label.toLowerCase()}?`,
      answer: answerWhyStatus(post),
      chips,
    },
    { id: "changed", label: "What changed recently?", answer: answerWhatChanged(post), chips },
    {
      id: "baseline",
      label: "How does this compare to the creator's usual pace?",
      answer: answerBaselineComparison(post),
    },
    { id: "alert", label: "Was an alert sent?", answer: answerAlertStatus(post.alert_sent, post.is_gone) },
    {
      id: "next",
      label: "What should I consider doing next?",
      answer: answerNextSteps(post.status_label, post.is_gone),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <StatusPill label={post.status_label} />
        <p className="mt-3 text-sm font-medium text-ink">@{post.creator.handle}</p>
        {post.caption && <p className="mt-1 line-clamp-2 text-sm text-ink-muted">"{post.caption}"</p>}
      </div>

      <QuestionList key={post.post_id} questions={questions} />
    </div>
  );
}

// Accordion of pre-built questions — one open at a time, first question
// open by default so the panel never starts as an empty prompt box.
function QuestionList({ questions }: { questions: QuestionItem[] }) {
  const [openId, setOpenId] = useState<string | null>(questions[0]?.id ?? null);

  return (
    <div className="space-y-2">
      {questions.map((q) => {
        const isOpen = q.id === openId;
        return (
          <div key={q.id} className="rounded-lg border border-line">
            <button
              type="button"
              onClick={() => setOpenId(isOpen ? null : q.id)}
              className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm text-ink transition-colors hover:bg-black/[0.02]"
            >
              <span>{q.label}</span>
              <span className="shrink-0 text-ink-muted">{isOpen ? "−" : "+"}</span>
            </button>
            {isOpen && (
              <div className="border-t border-line px-3 py-2.5">
                <p className="text-sm text-ink-muted">{q.answer}</p>
                {q.chips && q.chips.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {q.chips.map((chip) => (
                      <span
                        key={chip}
                        className="rounded-full bg-black/[0.04] px-2 py-0.5 text-[11px] text-ink-muted"
                      >
                        {chip}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-3 w-2/3 animate-pulse rounded bg-black/[0.04]" />
      <div className="h-3 w-1/2 animate-pulse rounded bg-black/[0.04]" />
      <div className="h-10 w-full animate-pulse rounded-lg bg-black/[0.04]" />
      <div className="h-10 w-full animate-pulse rounded-lg bg-black/[0.04]" />
    </div>
  );
}
