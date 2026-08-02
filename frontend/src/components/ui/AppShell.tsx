import { Outlet } from "react-router-dom";
import { Nav } from "./Nav";
import { AiPanel } from "./AiPanel";

// Two floating translucent cards on the gradient canvas, with the canvas
// itself only visible as the gap/frame around and between them: one wide
// card holding the nav + whichever page is selected (nav separated from
// the page by an internal hairline, not its own card), and one narrower
// card for the AI teammate. Both viewport-height-bound with their own
// internal scroll, so the shell itself never scrolls as a whole page.
export function AppShell() {
  return (
    <div className="flex h-screen gap-4 p-4 sm:gap-6 sm:p-8">
      <div className="flex min-w-0 flex-1 overflow-hidden rounded-3xl border border-line bg-board shadow-[0_20px_60px_rgb(0_0_0_/_10%)] backdrop-blur-[24px]">
        <Nav />
        <main className="min-w-0 flex-1 overflow-y-auto px-6 py-10 sm:px-10">
          <Outlet />
        </main>
      </div>
      <div className="hidden w-[340px] shrink-0 overflow-hidden rounded-3xl border border-line bg-board shadow-[0_20px_60px_rgb(0_0_0_/_10%)] backdrop-blur-[24px] lg:flex lg:flex-col">
        <AiPanel />
      </div>
    </div>
  );
}
