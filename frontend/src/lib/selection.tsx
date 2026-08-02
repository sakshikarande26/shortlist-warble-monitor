import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { PostDetail } from "./types";

// The right-hand AI panel is persistent across navigation, but only
// PostDetail actually knows the full post (with evidence). Rather than
// thread post data through router state, PostDetail publishes whichever
// post it has loaded into this context, and clears it on unmount — so the
// panel always reflects "the post currently open in the center," however
// the user got there (from Home triage or from a creator's post list).
interface SelectionState {
  activePost: PostDetail | null;
  setActivePost: (post: PostDetail | null) => void;
}

const SelectionContext = createContext<SelectionState | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [activePost, setActivePost] = useState<PostDetail | null>(null);
  const value = useMemo(() => ({ activePost, setActivePost }), [activePost]);
  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

export function useSelection(): SelectionState {
  const ctx = useContext(SelectionContext);
  if (!ctx) throw new Error("useSelection must be used within a SelectionProvider");
  return ctx;
}
