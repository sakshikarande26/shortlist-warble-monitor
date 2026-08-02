import type { ReactNode } from "react";

// The board: translucent, blurred, softly shadowed, floating on the
// canvas. The center column's content — Home triage, a creator's roster,
// or a post's detail — always lives inside exactly one of these.
export function Board({ children }: { children: ReactNode }) {
  return (
    <div className="animate-fade-in rounded-3xl border border-line bg-board p-6 shadow-[0_8px_40px_rgb(0_0_0_/_6%)] backdrop-blur-[24px] sm:p-10">
      {children}
    </div>
  );
}
