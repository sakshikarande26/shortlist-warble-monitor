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
//
// Below the `lg` breakpoint (phones, iPad portrait) the 220px sidebar
// doesn't fit alongside real content, so it becomes a slide-in drawer
// toggled from TopBar's hamburger button instead of a persistent column.
// `isNavOpen` only matters below `lg` — Nav ignores it entirely at `lg`
// and up, where it's always the static, always-visible sidebar.
export function AppShell() {
  const [isAgentOpen, setIsAgentOpen] = useState(false);
  const [isNavOpen, setIsNavOpen] = useState(false);

  return (
    <div className="relative flex h-screen flex-col gap-4 p-4 pb-9 sm:gap-6 sm:p-8 sm:pb-10">
      <TopBar onToggleNav={() => setIsNavOpen((open) => !open)} />

      {/* backdrop-blur is lg-only on purpose: backdrop-filter establishes a
          CSS containing block for position:fixed descendants, which pulled
          the mobile Nav drawer's fixed positioning off the true viewport and
          into this card's own (clipped, padded) box instead — confirmed by
          screenshotting it in a real browser, not something a type-check
          would catch. Below lg, Nav is genuinely position:fixed and needs
          the viewport as its containing block; at lg it's position:static
          (in normal flow), so the blur returning there is inert either way. */}
      <div className="flex min-h-0 flex-1 overflow-hidden rounded-3xl border border-line bg-board shadow-[0_20px_60px_rgb(0_0_0_/_10%)] lg:backdrop-blur-[24px]">
        {isNavOpen && (
          <div
            onClick={() => setIsNavOpen(false)}
            aria-hidden="true"
            className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          />
        )}
        <Nav
          isAgentOpen={isAgentOpen}
          isOpen={isNavOpen}
          onOpenAgent={() => setIsAgentOpen(true)}
          onClose={() => setIsNavOpen(false)}
          onNavigate={() => {
            setIsAgentOpen(false);
            setIsNavOpen(false);
          }}
        />
        {isAgentOpen ? (
          <AiPanel onClose={() => setIsAgentOpen(false)} />
        ) : (
          <main className="min-w-0 flex-1 overflow-y-auto px-4 py-8 sm:px-10 sm:py-10">
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
