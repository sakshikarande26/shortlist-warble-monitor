import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Nav } from "./Nav";
import { AiPanel } from "./AiPanel";

// Two floating translucent glass cards on the gradient canvas, with the
// canvas itself only visible as the gap/frame around and between them: one
// wide card holding the nav + whichever page is selected, and one
// narrower card for the marketing agent chat. The agent card is never
// persistent — it opens from the right on demand (compressing the main
// card via flex reflow) and a slim edge tab reopens it once closed.
export function AppShell() {
  const [isAgentOpen, setIsAgentOpen] = useState(false);

  return (
    <div className="flex h-screen gap-4 p-4 sm:gap-6 sm:p-8">
      <div className="flex min-w-0 flex-1 overflow-hidden rounded-3xl border border-line bg-board shadow-[0_20px_60px_rgb(0_0_0_/_10%)] backdrop-blur-[24px]">
        <Nav />
        <main className="min-w-0 flex-1 overflow-y-auto px-6 py-10 sm:px-10">
          <Outlet />
        </main>
      </div>

      {isAgentOpen ? (
        <div className="hidden w-[340px] shrink-0 overflow-hidden rounded-3xl border border-line bg-board shadow-[0_20px_60px_rgb(0_0_0_/_10%)] backdrop-blur-[24px] lg:flex lg:flex-col">
          <AiPanel onClose={() => setIsAgentOpen(false)} />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setIsAgentOpen(true)}
          className="hidden shrink-0 self-center rounded-full border border-line bg-board px-3 py-4 text-xs font-medium tracking-wide text-ink shadow-[0_8px_24px_rgb(0_0_0_/_8%)] backdrop-blur-[24px] transition-colors hover:border-accent hover:text-accent lg:block"
          style={{ writingMode: "vertical-rl" }}
        >
          Marketing agent
        </button>
      )}
    </div>
  );
}
