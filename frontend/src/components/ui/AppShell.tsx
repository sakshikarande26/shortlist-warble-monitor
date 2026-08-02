import { Outlet } from "react-router-dom";
import { Nav } from "./Nav";
import { AiPanel } from "./AiPanel";
import { Board } from "./Board";

// The three-column shell: a slim nav rail, the floating board (whichever
// section is selected), and a persistent AI notes rail. Nav and AI panel
// are flat — hairline dividers only — so only the center board gets the
// translucent/blurred/shadowed treatment.
export function AppShell() {
  return (
    <div className="flex min-h-screen bg-canvas">
      <Nav />
      <main className="min-w-0 flex-1 px-6 py-10 sm:px-10">
        <Board>
          <Outlet />
        </Board>
      </main>
      <AiPanel />
    </div>
  );
}
