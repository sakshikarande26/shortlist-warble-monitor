import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSelection } from "../../lib/selection";
import { useAgentChat } from "../../lib/agentChat";
import { evidenceChips } from "../../lib/copy";

interface AiPanelProps {
  onClose: () => void;
}

const POST_PROMPTS = [
  "Why does this matter?",
  "Sustained or just a spike?",
  "What should I check first?",
  "What would change your read?",
];

const PROGRAM_PROMPTS = [
  "What changed while I was away?",
  "What deserves attention first?",
  "Which creators are performing?",
  "What have we alerted on so far?",
];

export function AiPanel({ onClose }: AiPanelProps) {
  const { activePost } = useSelection();
  const { messages, isSending, send, endChat } = useAgentChat();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isSending]);

  const prompts = activePost ? POST_PROMPTS : PROGRAM_PROMPTS;
  const chips = activePost ? evidenceChips(activePost.evidence) : [];

  function ask(text: string) {
    void send(text, activePost?.post_id ?? null);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isSending) return;
    setInput("");
    ask(text);
  }

  return (
    <div className="flex h-full min-h-0 flex-col px-6 py-6">
      <div className="mb-4 flex shrink-0 items-start justify-between gap-2">
        <div>
          <div className="flex items-baseline gap-1.5">
            <p className="text-[15px] font-semibold tracking-tight text-ink">Marketing Agent</p>
            <p className="text-[11px] text-ink-muted">by Shortlist</p>
          </div>
          <p className="mt-0.5 text-xs text-ink-muted">
            {activePost ? `Looking at @${activePost.creator.handle}'s post` : "Looking at your whole program"}
          </p>
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

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.length === 0 ? <Intro /> : messages.map((m) => <Bubble key={m.id} message={m} />)}
        {isSending && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-black/[0.045] px-3 py-2 text-sm text-ink-muted">Thinking…</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {chips.length > 0 && (
        <div className="mt-3 shrink-0 border-t border-line pt-3">
          <p className="mb-1.5 text-[10px] tracking-wider text-ink-muted uppercase">
            What I'm reading from
          </p>
          <div className="flex flex-wrap gap-1.5">
            {chips.map((chip) => (
              <span key={chip} className="rounded-full bg-black/[0.05] px-2 py-0.5 text-[11px] text-ink-muted">
                {chip}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 flex shrink-0 flex-wrap gap-1.5">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            disabled={isSending}
            onClick={() => ask(prompt)}
            className="rounded-full border border-line px-2.5 py-1 text-xs text-ink transition-colors hover:border-ink/30 disabled:opacity-40"
          >
            {prompt}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="mt-3 flex shrink-0 items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your program…"
          className="min-w-0 flex-1 rounded-full border border-line bg-white/70 px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-ink/30 focus:outline-none"
        />
        <button
          type="submit"
          disabled={isSending || !input.trim()}
          className="shrink-0 rounded-full bg-ink px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-30"
        >
          Ask
        </button>
      </form>
    </div>
  );
}

function Intro() {
  return (
    <div className="space-y-3 text-sm text-ink-muted">
      <p className="text-sm font-medium text-ink">Your analyst, not your boss.</p>
      <p>
        I read every post's numbers so you don't have to, then tell you what's moving, what it
        probably means, and what a reasonable person might do next.
      </p>
      <p>
        What I won't do is make the call. I don't pull budget, I don't sign creators, and I don't
        decide what counts as a breakout. The detector handles that, and it's better at arithmetic
        than I am.
      </p>
      <p>Ask me anything. I only speak in facts I've actually been handed.</p>
    </div>
  );
}

function Bubble({ message }: { message: { role: "user" | "agent"; text: string; offline?: boolean } }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[88%] ${isUser ? "" : "flex gap-2"}`}>
        {!isUser && (
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink text-[10px] font-medium text-white">
            S
          </span>
        )}
        <div>
          <div
            className={`rounded-2xl px-3 py-2 text-sm ${
              isUser ? "bg-ink text-white" : "bg-black/[0.045] text-ink"
            }`}
          >
            {message.text}
          </div>
          {message.offline && (
            <p className="mt-1 text-[11px] text-ink-muted">Running offline, straight from the numbers.</p>
          )}
        </div>
      </div>
    </div>
  );
}
