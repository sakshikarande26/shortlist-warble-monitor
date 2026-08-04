import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSelection } from "../../lib/selection";
import { useAgentChat, type AgentMessage } from "../../lib/agentChat";
import { agentEvidenceChips } from "../../lib/copy";

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
// skin. Fill is the strict palette's "Warm Sand" neutral; the border has
// no dedicated palette swatch, so it stays the same translucent-black
// hairline used everywhere else rather than inventing an off-palette hex.
const WARM_BORDER = "border-line";
const WARM_FILL = "bg-[#fcf1e9]";

// Lives inside the main content card (AppShell renders this in place of
// the routed page when open) as a two-column workspace: a compact chat on
// the left, a comparatively bigger evidence panel on the right — never a
// separate floating card. The evidence panel shows exactly what grounded
// the most recent reply, so the chat's claims and the proof sit side by
// side instead of the proof being buried in tiny inline chips.
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

  const prompts = activePost ? POST_PROMPTS : PROGRAM_PROMPTS;
  const lastAssistantMessage = [...messages].reverse().find((m) => m.role === "agent");

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
      <div className={`flex h-full min-h-0 w-full max-w-[400px] shrink-0 flex-col border-r ${WARM_BORDER} px-5 py-5`}>
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
          {messages.length === 0 ? <Intro /> : messages.map((m) => <Bubble key={m.id} message={m} />)}
          {isSending && !pendingPrompt && (
            <div className="flex justify-start">
              <div className={`rounded-2xl border ${WARM_BORDER} bg-white px-3 py-2 text-sm text-ink-muted`}>
                Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="mt-2.5 flex shrink-0 flex-wrap gap-1.5">
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
            className="shrink-0 rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-white shadow-[0_2px_8px_rgb(109_93_245_/_35%)] transition-all hover:bg-accent/90 hover:shadow-[0_2px_12px_rgb(109_93_245_/_45%)] active:scale-[0.97] disabled:bg-black/10 disabled:text-ink-muted disabled:shadow-none disabled:active:scale-100"
          >
            Ask
          </button>
        </form>
      </div>

      {/* Evidence — comparatively bigger, right */}
      <EvidencePanel message={lastAssistantMessage} />
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

function Bubble({ message }: { message: AgentMessage }) {
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
            <p className="mt-1 flex items-center gap-1 pl-0.5 text-[10px] font-medium tracking-wide text-ink-muted">
              <span className={`h-1 w-1 rounded-full ${message.offline ? "bg-ink-muted/50" : "bg-accent"}`} />
              {message.offline ? "Offline · from the numbers" : "Live"}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// The evidence behind the most recent reply, laid out as a few real,
// legible facts rather than a wall of tiny chips — this is the panel the
// chat's claims are supposed to be checkable against.
function EvidencePanel({ message }: { message: AgentMessage | undefined }) {
  const chips = message ? agentEvidenceChips(message.factsUsed) : [];

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto p-6 sm:p-8">
      <p className="text-[15px] font-semibold text-ink">Evidence</p>
      <p className="mt-0.5 text-sm text-ink-muted">What the last answer is grounded in — nothing more.</p>

      {chips.length === 0 ? (
        <div className="mt-8 flex flex-1 items-center justify-center rounded-2xl border border-dashed border-line text-center text-sm text-ink-muted">
          Ask a question to see the real numbers behind the answer.
        </div>
      ) : (
        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {chips.map((chip) => (
            <div key={chip} className="rounded-2xl border border-line bg-white p-5">
              <p className="text-lg leading-snug font-bold tracking-tight text-ink">{chip}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
