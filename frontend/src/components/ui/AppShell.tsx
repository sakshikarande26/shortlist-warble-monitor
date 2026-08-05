import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Nav } from "./Nav";
import { AiPanel } from "./AiPanel";
import { TopBar } from "./TopBar";

// A full-width glass TopBar, then one floating translucent glass card on
// the gradient canvas below it holding the nav plus whichever content is
// active. The marketing agent is never a separate floating card of its
// own — opening it (from the sidebar's "Marketing agent" item) swaps the
// routed page for the agent workspace inside this same card; closing it
// returns to the page that was showing.
export function AppShell() {
  const [isAgentOpen, setIsAgentOpen] = useState(false);

  return (
    <div className="relative flex h-screen flex-col gap-4 p-4 pb-9 sm:gap-6 sm:p-8 sm:pb-10">
      <TopBar />

      <div className="flex min-h-0 flex-1 overflow-hidden rounded-3xl border border-line bg-board shadow-[0_20px_60px_rgb(0_0_0_/_10%)] backdrop-blur-[24px]">
        <Nav
          isAgentOpen={isAgentOpen}
          onOpenAgent={() => setIsAgentOpen(true)}
          onNavigate={() => setIsAgentOpen(false)}
        />
        {isAgentOpen ? (
          <AiPanel onClose={() => setIsAgentOpen(false)} />
        ) : (
          <main className="min-w-0 flex-1 overflow-y-auto px-6 py-10 sm:px-10">
            <Outlet />
          </main>
        )}
      </div>
      <p className="absolute bottom-2 left-1/2 -translate-x-1/2 text-center text-[10px] text-ink-muted">
        © Sakshi Karande
      </p>
    </div>
  );
}
