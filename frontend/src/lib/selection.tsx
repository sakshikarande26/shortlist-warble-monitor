import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { CreatorDetailResponse, PostDetail } from "./types";

// The right-hand teammate panel is persistent across navigation, but only
// PostDetail/CreatorDetail actually know the full record (with evidence).
// Rather than thread data through router state, those pages publish
// whichever record they've loaded into this context, and clear it on
// unmount — so the panel always reflects "what's open in the center,"
// however the user got there. A selected post takes priority over a
// selected creator (more specific context wins) when, briefly, both could
// be set during a route transition.
interface SelectionState {
  activePost: PostDetail | null;
  setActivePost: (post: PostDetail | null) => void;
  activeCreator: CreatorDetailResponse | null;
  setActiveCreator: (creator: CreatorDetailResponse | null) => void;
}

const SelectionContext = createContext<SelectionState | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [activePost, setActivePost] = useState<PostDetail | null>(null);
  const [activeCreator, setActiveCreator] = useState<CreatorDetailResponse | null>(null);
  const value = useMemo(
    () => ({ activePost, setActivePost, activeCreator, setActiveCreator }),
    [activePost, activeCreator],
  );
  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

export function useSelection(): SelectionState {
  const ctx = useContext(SelectionContext);
  if (!ctx) throw new Error("useSelection must be used within a SelectionProvider");
  return ctx;
}
