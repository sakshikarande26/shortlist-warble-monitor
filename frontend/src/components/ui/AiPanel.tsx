import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useSelection } from "../../lib/selection";
import { useAgentChat, type AgentMessage } from "../../lib/agentChat";
import { agentProgramContext, agentReferences, type AgentReference } from "../../lib/copy";
import { StatusPill } from "./StatusPill";

interface AiPanelProps {
  onClose: () => void;
}

const POST_PROMPTS = [
  "Why does this matter?",
  "Sustained or a spike?",
  "Explain this for leadership",
  "What would change your read?",
];

const PROGRAM_PROMPTS = [
  "What changed since I checked?",
  "What deserves attention first?",
  "Give me a stakeholder update",
  "What have we alerted on so far?",
];

// Warm-neutral surfaces scoped to this workspace only — the outer glass
// card (AppShell) stays the shared white/blur look everywhere else in the
// app; this is the one place that gets its own distinct, premium-feeling
// skin. The border has no dedicated palette swatch, so it stays the same
// translucent-black hairline used everywhere else.
const WARM_BORDER = "border-line";
const WARM_FILL = "bg-white/45 backdrop-blur-[10px]";

// Lives inside the main content card (AppShell renders this in place of
// the routed page when open) as a two-column workspace: a compact chat on
// the left, a comparatively bigger references panel on the right — never a
// separate floating card. Each answer is numbered, and its number appears
// on both the chat bubble and its reference group, so a claim and the
// posts it was drawn from stay tied together without repeating the
// question text on both sides.
export function AiPanel({ onClose }: AiPanelProps) {
  const { activePost } = useSelection();
  const { messages, isSending, send, greet, endChat } = useAgentChat();
  const [input, setInput] = useState("");
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Guards the one-time opening line against React StrictMode's dev-mode
  // double-invoke of mount effects — without this, the async greet() call
  // fires twice before the first reply lands and messages.length is still
  // 0 for both, producing two identical opening messages.
  const hasGreetedRef = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isSending]);

  // Opens with something already said, not a blank "how can I help" —
  // fires once, only on a genuinely fresh conversation (never replays on
  // a reopen once there's real history).
  useEffect(() => {
    if (messages.length === 0 && !hasGreetedRef.current) {
      hasGreetedRef.current = true;
      void greet(activePost?.post_id ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Once a suggested prompt has actually been asked (as a real user turn,
  // however it was sent — clicked or typed), it drops out of the
  // suggestion row rather than sitting there inviting a duplicate ask.
  const askedPrompts = new Set(messages.filter((m) => m.role === "user").map((m) => m.text));
  const prompts = (activePost ? POST_PROMPTS : PROGRAM_PROMPTS).filter((p) => !askedPrompts.has(p));

  // Number every assistant reply once, here, so the chat bubble and the
  // reference group can cite the same number.
  const replyNumbers = new Map<string, number>();
  messages.filter((m) => m.role === "agent").forEach((m, i) => replyNumbers.set(m.id, i + 1));

  function ask(text: string) {
    setPendingPrompt(text);
    void send(text, activePost?.post_id ?? null).finally(() => setPendingPrompt(null));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isSending) return;
    setInput("");
    ask(text);
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1">
      {/* Chat — compact, left */}
      <div
        className={`agent-pastel-bg flex h-full min-h-0 w-full max-w-[400px] shrink-0 flex-col border-r ${WARM_BORDER} px-5 py-5`}
      >
        <div className={`mb-3 flex shrink-0 items-center justify-between gap-2 border-b ${WARM_BORDER} pb-3`}>
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-white">
              S
            </span>
            <div className="min-w-0">
              <p className="text-[14px] font-semibold leading-tight tracking-tight text-ink">
                Marketing Agent
              </p>
              <p className="truncate text-[11px] leading-tight text-ink-muted">
                {activePost ? `@${activePost.creator.handle}'s post` : "Whole program"}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {messages.length > 0 && (
              <button
                type="button"
                onClick={() => void endChat()}
                className="rounded-full px-2 py-1 text-[11px] text-ink-muted transition-colors hover:bg-black/[0.05] hover:text-ink"
              >
                End chat
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close marketing agent"
              className="rounded-full p-1.5 text-ink-muted transition-colors hover:bg-black/[0.05] hover:text-ink"
            >
              ×
            </button>
          </div>
        </div>

        <div className={`min-h-0 flex-1 space-y-2.5 overflow-y-auto rounded-2xl ${WARM_FILL} p-3`}>
          {messages.length === 0 ? (
            <Intro />
          ) : (
            messages.map((m) => (
              <Bubble key={m.id} message={m} replyNumber={replyNumbers.get(m.id) ?? null} />
            ))
          )}
          {isSending && !pendingPrompt && (
            <div className="flex justify-start">
              <div className={`rounded-2xl border ${WARM_BORDER} bg-white px-3 py-2 text-sm text-ink-muted`}>
                Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="mt-2.5 flex shrink-0 flex-wrap gap-1.5 empty:hidden">
          {prompts.map((prompt) => {
            const isPending = isSending && pendingPrompt === prompt;
            return (
              <button
                key={prompt}
                type="button"
                disabled={isSending}
                onClick={() => ask(prompt)}
                className={`rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-1 disabled:cursor-default ${
                  isPending
                    ? "border-accent/50 bg-accent-soft text-accent"
                    : `${WARM_BORDER} bg-white text-ink-muted hover:border-accent/40 hover:bg-accent-soft hover:text-accent disabled:opacity-40 disabled:hover:border-line disabled:hover:bg-white disabled:hover:text-ink-muted`
                }`}
              >
                {isPending ? "Thinking…" : prompt}
              </button>
            );
          })}
        </div>

        <form onSubmit={handleSubmit} className="mt-2.5 flex shrink-0 items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your program…"
            className={`min-w-0 flex-1 rounded-full border ${WARM_BORDER} bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-ink-muted/70 focus:border-accent/50 focus:ring-2 focus:ring-accent/20 focus:outline-none`}
          />
          <button
            type="submit"
            disabled={isSending || !input.trim()}
            className="shrink-0 rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-white shadow-[0_2px_8px_rgb(0_0_0_/_20%)] transition-all hover:bg-accent/90 hover:shadow-[0_2px_12px_rgb(0_0_0_/_28%)] active:scale-[0.97] disabled:bg-black/10 disabled:text-ink-muted disabled:shadow-none disabled:active:scale-100"
          >
            Ask
          </button>
        </form>
      </div>

      {/* References — comparatively bigger, right */}
      <ReferencesPanel
        replies={messages
          .filter((m) => m.role === "agent")
          .map((m) => ({ message: m, number: replyNumbers.get(m.id) ?? 0 }))
          .reverse()}
      />
    </div>
  );
}

function Intro() {
  return (
    <div className="space-y-1 p-1 text-sm text-ink-muted">
      <p className="text-sm font-semibold text-ink">Your analyst, not your boss.</p>
      <p>I read the numbers and tell you what they mean. Ask me anything.</p>
    </div>
  );
}

function Bubble({ message, replyNumber }: { message: AgentMessage; replyNumber: number | null }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[88%] ${isUser ? "" : "flex gap-2"}`}>
        {!isUser && (
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent text-[10px] font-medium text-white">
            S
          </span>
        )}
        <div className="min-w-0">
          <div
            className={`rounded-2xl px-3 py-2 text-sm ${
              isUser
                ? "bg-[#0f1115] text-white"
                : `border ${WARM_BORDER} bg-white text-ink shadow-[0_1px_2px_rgb(0_0_0_/_4%)]`
            }`}
          >
            {message.text}
          </div>
          {!isUser && (
            <p className="mt-1 flex items-center gap-1.5 pl-0.5 text-[10px] font-medium tracking-wide text-ink-muted">
              <span className={`h-1 w-1 rounded-full ${message.offline ? "bg-ink-muted/50" : "bg-accent"}`} />
              {message.offline ? "Offline · from the numbers" : "Live"}
              {replyNumber !== null && (
                <span className="rounded-full border border-line bg-white px-1.5 text-[9px] text-ink-muted">
                  {replyNumber}
                </span>
              )}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// Every answer's sources, newest first — the post each claim was actually
// about, with that post's own numbers, clickable through to the full
// detail page. Answers whose facts resolved to nothing citable are simply
// left out rather than padded with program totals.
function ReferencesPanel({ replies }: { replies: { message: AgentMessage; number: number }[] }) {
  const groups = replies
    .map((reply) => ({
      ...reply,
      references: agentReferences(reply.message.text, reply.message.factsUsed),
      context: agentProgramContext(reply.message.factsUsed),
    }))
    .filter((group) => group.references.length > 0 || group.message.reasoning);

  return (
    <div className="agent-pastel-bg-soft flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="shrink-0 border-b border-line px-6 py-5 sm:px-8">
        <p className="text-[15px] font-semibold text-ink">The read</p>
        <p className="mt-0.5 text-sm text-ink-muted">
          The thinking behind each answer, and the posts it came from. Open one to inspect it in full.
        </p>
      </div>

      {groups.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-ink-muted">
          Ask a question — the reasoning and the posts behind the answer show up here.
        </div>
      ) : (
        <div className="min-h-0 flex-1 divide-y divide-line overflow-y-auto">
          {groups.map((group) => (
            <div key={group.message.id} className="px-6 py-5 sm:px-8">
              <div className="mb-3 flex items-center gap-2">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink text-[10px] font-semibold text-white">
                  {group.number}
                </span>
                {group.references.length > 0 && (
                  <span className="text-[11px] font-medium tracking-wider text-ink-muted uppercase">
                    {group.references.length} source{group.references.length === 1 ? "" : "s"}
                  </span>
                )}
                {group.context && (
                  <span className="ml-auto truncate text-[11px] text-ink-muted">{group.context}</span>
                )}
              </div>

              {group.message.reasoning && (
                <p className="mb-3 text-sm leading-relaxed text-ink">{group.message.reasoning}</p>
              )}

              {group.references.length > 0 && (
                <div className="space-y-2">
                  {group.references.map((reference) => (
                    <ReferenceCard key={`${group.message.id}-${reference.handle}`} reference={reference} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ReferenceCard({ reference }: { reference: AgentReference }) {
  const body = (
    <>
      <div className="flex items-center gap-2">
        <span className="truncate text-sm font-medium text-ink">@{reference.handle}</span>
        {reference.status && <StatusPill label={reference.status} />}
      </div>
      {reference.caption && (
        <p className="mt-0.5 truncate text-xs text-ink-muted">"{reference.caption}"</p>
      )}
      {reference.facts.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {reference.facts.map((fact) => (
            <span
              key={fact}
              className="rounded-full border border-line bg-white px-2 py-0.5 text-[11px] font-medium text-ink"
            >
              {fact}
            </span>
          ))}
        </div>
      )}
    </>
  );

  if (!reference.postId) {
    return <div className="rounded-2xl border border-line bg-white/70 p-4">{body}</div>;
  }
  return (
    <Link
      to={`/posts/${reference.postId}`}
      className="block rounded-2xl border border-line bg-white/70 p-4 transition-colors hover:border-ink/20 hover:bg-white"
    >
      {body}
    </Link>
  );
}
