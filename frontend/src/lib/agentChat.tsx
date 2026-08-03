import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { endAgentSession, sendAgentMessage } from "./api";

export interface AgentMessage {
  id: string;
  role: "user" | "agent";
  text: string;
  offline?: boolean;
}

interface AgentChatState {
  messages: AgentMessage[];
  isSending: boolean;
  send: (message: string, selectedPostId: string | null) => Promise<void>;
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
        { id: `a-${Date.now()}`, role: "agent", text: reply.text, offline: !reply.llm_available },
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
    () => ({ messages, isSending, send, endChat }),
    [messages, isSending, send, endChat],
  );
  return <AgentChatContext.Provider value={value}>{children}</AgentChatContext.Provider>;
}

export function useAgentChat(): AgentChatState {
  const ctx = useContext(AgentChatContext);
  if (!ctx) throw new Error("useAgentChat must be used within an AgentChatProvider");
  return ctx;
}
