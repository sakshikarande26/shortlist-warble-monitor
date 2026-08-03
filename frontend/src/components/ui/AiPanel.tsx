import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSelection } from "../../lib/selection";
import {
  answerAlertStatus,
  answerBaselineComparison,
  answerCreatorNeedsAttention,
  answerCreatorOutperforming,
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
import type { CreatorDetailResponse, HomeResponse, PostDetail, SystemStatus } from "../../lib/types";
import { StatusPill } from "./StatusPill";

interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  text: string;
  chips?: string[];
}

interface SuggestedQuestion {
  id: string;
  label: string;
  answer: string;
  chips?: string[];
}

type IdleLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; systemStatus: SystemStatus; home: HomeResponse };

interface AiPanelProps {
  onClose: () => void;
}

// The teammate is a chat interface, not an accordion: a message thread
// seeded with predefined marketing questions as suggestion chips (no LLM
// wired up yet, see lib/copy.ts), plus a free-text box that falls back to
// grounded keyword matching against the same known questions rather than
// pretending to understand anything it wasn't given real data for. Three
// contexts share the same thread component: nothing selected (the whole
// program), a creator selected, or a post selected.
export function AiPanel({ onClose }: AiPanelProps) {
  const { activePost, activeCreator } = useSelection();
  const [idleState, setIdleState] = useState<IdleLoadState>({ status: "loading" });

  useEffect(() => {
    if (activePost || activeCreator) return;
    setIdleState({ status: "loading" });
    Promise.all([getStatus(), getHome()])
      .then(([systemStatus, home]) => setIdleState({ status: "ready", systemStatus, home }))
      .catch(() => setIdleState({ status: "error" }));
  }, [activePost, activeCreator]);

  const mode = activePost ? "post" : activeCreator ? "creator" : "idle";

  return (
    <div className="flex h-full min-h-0 flex-col px-6 py-6">
      <div className="mb-4 flex shrink-0 items-center justify-between">
        <div>
          <div className="flex items-baseline gap-1.5">
            <p className="text-[15px] font-semibold tracking-tight text-ink">Marketing Agent</p>
            <p className="text-[11px] text-ink-muted">by Shortlist</p>
          </div>
          <p className="mt-0.5 text-xs text-ink-muted">
            {mode === "post"
              ? "Ask me anything about this post"
              : mode === "creator"
                ? "Ask me anything about this creator"
                : "Ask me anything about your program"}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close marketing agent"
          className="shrink-0 rounded-full p-1.5 text-ink-muted transition-colors hover:bg-black/[0.05] hover:text-ink"
        >
          ×
        </button>
      </div>

      {mode === "post" && activePost && <PostChat post={activePost} />}
      {mode === "creator" && activeCreator && <CreatorChat detail={activeCreator} />}
      {mode === "idle" && <IdleChat state={idleState} />}
    </div>
  );
}

function IdleChat({ state }: { state: IdleLoadState }) {
  if (state.status === "loading") return <PanelSkeleton />;
  if (state.status === "error") {
    return <p className="text-sm text-ink-muted">Couldn't load your program's status.</p>;
  }

  const { systemStatus, home } = state;
  const suggestions: SuggestedQuestion[] = [
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
    { id: "alert", label: "Was an alert sent recently?", answer: answerRecentAlert(systemStatus) },
  ];
  const progress =
    systemStatus.last_checked_sim_hours !== null
      ? formatMonitoringProgress(systemStatus.last_checked_sim_hours)
      : "the start of monitoring";
  const greeting = `Hi. I'm watching ${systemStatus.posts_tracked} post${systemStatus.posts_tracked === 1 ? "" : "s"} across your creator program (${progress}). Ask me anything below.`;

  return <ChatThread greeting={greeting} suggestions={suggestions} resetKey="idle" />;
}

function CreatorChat({ detail }: { detail: CreatorDetailResponse }) {
  const suggestions: SuggestedQuestion[] = [
    {
      id: "attention",
      label: "Which of this creator's posts needs attention?",
      answer: answerCreatorNeedsAttention(detail),
    },
    {
      id: "outperforming",
      label: "Are they outperforming their usual pace?",
      answer: answerCreatorOutperforming(detail),
    },
  ];
  const greeting = `Here's what I can tell you about @${detail.creator.handle}.`;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-3 flex shrink-0 items-center gap-2">
        <span className="truncate text-sm font-medium text-ink">@{detail.creator.handle}</span>
      </div>
      <ChatThread greeting={greeting} suggestions={suggestions} resetKey={`creator-${detail.creator.id}`} />
    </div>
  );
}

function PostChat({ post }: { post: PostDetail }) {
  const chips = evidenceChips(post.evidence);
  const suggestions: SuggestedQuestion[] = [
    { id: "why", label: `Why is this ${post.status_label.toLowerCase()}?`, answer: answerWhyStatus(post), chips },
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
  const greeting = `Here's what I can tell you about @${post.creator.handle}'s post.`;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-3 flex shrink-0 items-center gap-2">
        <StatusPill label={post.status_label} />
        <span className="truncate text-sm font-medium text-ink">@{post.creator.handle}</span>
      </div>
      <ChatThread greeting={greeting} suggestions={suggestions} resetKey={`post-${post.post_id}`} />
    </div>
  );
}

// The message thread + suggestion chips + free-text input, shared by all
// three contexts. Resets to a fresh conversation whenever resetKey changes
// (a different post/creator, or back to idle) rather than accumulating an
// unrelated thread.
function ChatThread({
  greeting,
  suggestions,
  resetKey,
}: {
  greeting: string;
  suggestions: SuggestedQuestion[];
  resetKey: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([{ id: "greeting", role: "assistant", text: greeting }]);
  const [askedIds, setAskedIds] = useState<Set<string>>(new Set());
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([{ id: "greeting", role: "assistant", text: greeting }]);
    setAskedIds(new Set());
    // Only reset when the subject actually changes, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function ask(question: SuggestedQuestion) {
    setMessages((prev) => [
      ...prev,
      { id: `${question.id}-q`, role: "user", text: question.label },
      { id: `${question.id}-a`, role: "assistant", text: question.answer, chips: question.chips },
    ]);
    setAskedIds((prev) => new Set(prev).add(question.id));
  }

  function handleSend(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text) return;
    const match = matchSuggestion(text, suggestions);
    setMessages((prev) => [
      ...prev,
      { id: `free-${prev.length}`, role: "user", text },
      match
        ? { id: `free-${prev.length}-a`, role: "assistant", text: match.answer, chips: match.chips }
        : {
            id: `free-${prev.length}-a`,
            role: "assistant",
            text: "I can only answer grounded questions about real data right now. Try one of the suggestions below.",
          },
    ]);
    setInput("");
  }

  const remaining = suggestions.filter((q) => !askedIds.has(q.id));

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.map((message) => (
          <ChatBubble key={message.id} message={message} />
        ))}
        <div ref={bottomRef} />
      </div>

      {remaining.length > 0 && (
        <div className="mt-3 flex shrink-0 flex-wrap gap-1.5">
          {remaining.map((q) => (
            <button
              key={q.id}
              type="button"
              onClick={() => ask(q)}
              className="rounded-full border border-line px-2.5 py-1 text-xs text-ink transition-colors hover:border-accent hover:text-accent"
            >
              {q.label}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSend} className="mt-3 flex shrink-0 items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask your teammate..."
          className="min-w-0 flex-1 rounded-full border border-line bg-white/70 px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          className="shrink-0 rounded-full bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent/90"
        >
          Send
        </button>
      </form>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${isUser ? "bg-accent text-white" : "bg-black/[0.045] text-ink"}`}
      >
        <p>{message.text}</p>
        {message.chips && message.chips.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message.chips.map((chip) => (
              <span
                key={chip}
                className={`rounded-full px-2 py-0.5 text-[11px] ${isUser ? "bg-white/20 text-white" : "bg-white/70 text-ink"}`}
              >
                {chip}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// No real language understanding, just keyword overlap against the known
// suggestions, so a free-typed question can still land on the right
// grounded answer instead of always falling back to "try a suggestion."
function matchSuggestion(input: string, suggestions: SuggestedQuestion[]): SuggestedQuestion | null {
  const normalized = input.toLowerCase();
  let best: { question: SuggestedQuestion; score: number } | null = null;
  for (const question of suggestions) {
    const words = question.label.toLowerCase().split(/\W+/).filter((w) => w.length > 3);
    const score = words.filter((w) => normalized.includes(w)).length;
    if (score > 0 && (!best || score > best.score)) {
      best = { question, score };
    }
  }
  return best ? best.question : null;
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
