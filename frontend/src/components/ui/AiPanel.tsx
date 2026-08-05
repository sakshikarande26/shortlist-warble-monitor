import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useSelection } from "../../lib/selection";
import { useAgentChat, type AgentMessage } from "../../lib/agentChat";
import { agentReferences, type AgentReference } from "../../lib/copy";
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

// One continuous column, not a chat-plus-side-panel split: each reply
// carries its own evidence directly beneath it, so there's nothing to keep
// paired across two surfaces. Lives inside the main content card (AppShell
// renders this in place of the routed page when open) — never a floating
// card of its own.
export function AiPanel({ onClose }: AiPanelProps) {
  const { activePost } = useSelection();
  const { messages, isSending, send, endChat } = useAgentChat();
  const [input, setInput] = useState("");
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isSending]);

  // Once a suggested prompt has actually been asked (as a real user turn,
  // however it was sent — clicked or typed), it drops out of the
  // suggestion row rather than sitting there inviting a duplicate ask.
  const askedPrompts = new Set(messages.filter((m) => m.role === "user").map((m) => m.text));
  const prompts = (activePost ? POST_PROMPTS : PROGRAM_PROMPTS).filter((p) => !askedPrompts.has(p));

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
    <div className="agent-pastel-bg flex h-full min-h-0 min-w-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-line px-6 py-4 sm:px-10">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-[12px] font-semibold text-white">
            S
          </span>
          <div className="min-w-0">
            <p className="text-[15px] font-semibold leading-tight tracking-tight text-ink">
              Marketing Agent
            </p>
            <p className="truncate text-[12px] leading-tight text-ink-muted">
              {activePost ? `@${activePost.creator.handle}'s post` : "Whole program"}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {messages.length > 0 && (
            <button
              type="button"
              onClick={() => void endChat()}
              className="rounded-full px-2.5 py-1 text-xs text-ink-muted transition-colors hover:bg-black/[0.05] hover:text-ink"
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

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 sm:px-10">
        <div className="mx-auto max-w-2xl space-y-5">
          {messages.length === 0 ? <Intro /> : messages.map((m) => <Turn key={m.id} message={m} />)}
          {isSending && !pendingPrompt && (
            <div className="flex gap-2.5">
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-medium text-white">
                S
              </span>
              <div className="rounded-2xl border border-line bg-white/70 px-3.5 py-2.5 text-sm text-ink-muted">
                Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="shrink-0 border-t border-line px-6 py-4 sm:px-10">
        <div className="mx-auto max-w-2xl">
          <div className="flex flex-wrap gap-1.5 empty:hidden">
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
                      : "border-line bg-white text-ink-muted hover:border-accent/40 hover:bg-accent-soft hover:text-accent disabled:opacity-40 disabled:hover:border-line disabled:hover:bg-white disabled:hover:text-ink-muted"
                  }`}
                >
                  {isPending ? "Thinking…" : prompt}
                </button>
              );
            })}
          </div>

          <form onSubmit={handleSubmit} className="mt-2.5 flex items-center gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your program…"
              className="min-w-0 flex-1 rounded-full border border-line bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-ink-muted/70 focus:border-accent/50 focus:ring-2 focus:ring-accent/20 focus:outline-none"
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
      </div>
    </div>
  );
}

function Intro() {
  return (
    <div className="space-y-1.5 p-1 text-sm text-ink-muted">
      <p className="text-sm font-semibold text-ink">
        The colleague who actually reads the full report before the meeting.
      </p>
      <p>I don't make the calls. I hand you what's worth knowing before you do.</p>
    </div>
  );
}

// One turn of the conversation. A user message is just the bubble. An
// assistant message is the bubble, a freshness line, and — directly
// beneath, still part of the same turn — an evidence card holding the
// strategic read and the posts it's grounded in. The card is solid white
// against the bubble's translucent white and the pastel wash behind
// everything, so it reads as the one firm surface in the turn: this part
// is checkable. Turns with nothing to cite render no card at all.
function Turn({ message }: { message: AgentMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-[#0f1115] px-4 py-2.5 text-sm text-white">
          {message.text}
        </div>
      </div>
    );
  }

  const references = agentReferences(message.text, message.factsUsed);
  const hasEvidence = Boolean(message.reasoning) || references.length > 0;

  return (
    <div className="flex gap-2.5">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-medium text-white">
        S
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="rounded-2xl border border-line bg-white/70 px-3.5 py-2.5 text-sm text-ink shadow-[0_1px_2px_rgb(0_0_0_/_4%)]">
          {message.text}
        </div>
        <p className="flex items-center gap-1.5 pl-0.5 text-[10px] font-medium tracking-wide text-ink-muted">
          <span className={`h-1 w-1 rounded-full ${message.offline ? "bg-ink-muted/50" : "bg-accent"}`} />
          {message.offline ? "Offline · from the numbers" : "Live"}
        </p>

        {hasEvidence && (
          <div className="rounded-2xl border border-line bg-white p-4 sm:p-5">
            {message.reasoning && (
              <div>
                <p className="text-[10px] font-medium tracking-wider text-ink-muted uppercase">
                  Why
                </p>
                <p className="mt-1 text-sm leading-relaxed text-ink">{message.reasoning}</p>
              </div>
            )}
            {references.length > 0 && (
              <div className={message.reasoning ? "mt-4 space-y-2 border-t border-line pt-3" : "space-y-2"}>
                <p className="text-[10px] font-medium tracking-wider text-ink-muted uppercase">
                  Sources
                </p>
                {references.map((reference) => (
                  <ReferenceCard key={reference.handle} reference={reference} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
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
              className="rounded-full border border-line bg-[#faf9f8] px-2 py-0.5 text-[11px] font-medium text-ink"
            >
              {fact}
            </span>
          ))}
        </div>
      )}
    </>
  );

  if (!reference.postId) {
    return <div className="rounded-xl border border-line bg-[#faf9f8] p-3">{body}</div>;
  }
  return (
    <Link
      to={`/posts/${reference.postId}`}
      className="block rounded-xl border border-line bg-[#faf9f8] p-3 transition-colors hover:border-ink/20 hover:bg-white"
    >
      {body}
    </Link>
  );
}
