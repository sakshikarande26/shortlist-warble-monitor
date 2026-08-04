import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { endAgentSession, sendAgentMessage } from "./api";

export interface AgentMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  offline?: boolean;
  // The exact facts_used behind this specific reply — kept per message
  // (not just off the currently selected post) so the evidence shown in
  // the UI always matches what actually grounded that turn.
  factsUsed?: Record<string, unknown>;
  // The strategic read behind this reply, shown in the references panel.
  reasoning?: string | null;
}

interface AgentChatState {
  messages: AgentMessage[];
  isSending: boolean;
  send: (message: string, selectedPostId: string | null) => Promise<void>;
  greet: (selectedPostId: string | null) => Promise<void>;
  endChat: () => Promise<void>;
}

const AgentChatContext = createContext<AgentChatState | null>(null);

// The conversation lives above the panel so it survives navigating between
// pages, selecting a different post, and closing/reopening the panel. It
// ends only when the user explicitly ends it.
export function AgentChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const sessionId = useRef(
    `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`,
  );

  const send = useCallback(async (message: string, selectedPostId: string | null) => {
    const trimmed = message.trim();
    if (!trimmed) return;

    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", text: trimmed }]);
    setIsSending(true);
    try {
      const reply = await sendAgentMessage({
        session_id: sessionId.current,
        message: trimmed,
        selected_post_id: selectedPostId ?? undefined,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "agent",
          text: reply.text,
          offline: !reply.llm_available,
          factsUsed: reply.facts_used,
          reasoning: reply.reasoning,
        },
      ]);
    } catch {
      // The panel is an assistant, not the product. A failure here shows a
      // calm line in the thread rather than an error state.
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "agent",
          text: "I couldn't reach the monitoring service just then. Try asking again.",
          offline: true,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }, []);

  // The opening line: fires once, automatically, when the panel is first
  // opened on a fresh conversation — no user bubble, since the manager
  // didn't ask anything. Same endpoint, same guardrails, just a different
  // trigger (see agent.py's `proactive` flag).
  const greet = useCallback(async (selectedPostId: string | null) => {
    setIsSending(true);
    try {
      const reply = await sendAgentMessage({
        session_id: sessionId.current,
        message: "",
        selected_post_id: selectedPostId ?? undefined,
        proactive: true,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "agent",
          text: reply.text,
          offline: !reply.llm_available,
          factsUsed: reply.facts_used,
          reasoning: reply.reasoning,
        },
      ]);
    } catch {
      // Silent — a failed opening line just leaves the static intro
      // showing, which is a fine fallback for a nice-to-have.
    } finally {
      setIsSending(false);
    }
  }, []);

  const endChat = useCallback(async () => {
    const previous = sessionId.current;
    sessionId.current = `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    setMessages([]);
    try {
      await endAgentSession(previous);
    } catch {
      // Server-side memory is best-effort; the local reset is what the
      // user actually asked for and has already happened.
    }
  }, []);

  const value = useMemo(
    () => ({ messages, isSending, send, greet, endChat }),
    [messages, isSending, send, greet, endChat],
  );
  return <AgentChatContext.Provider value={value}>{children}</AgentChatContext.Provider>;
}

export function useAgentChat(): AgentChatState {
  const ctx = useContext(AgentChatContext);
  if (!ctx) throw new Error("useAgentChat must be used within an AgentChatProvider");
  return ctx;
}
