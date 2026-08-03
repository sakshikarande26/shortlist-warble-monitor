import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/ui/AppShell";
import { SelectionProvider } from "./lib/selection";
import { Home } from "./pages/Home";
import { Creators } from "./pages/Creators";
import { CreatorDetail } from "./pages/CreatorDetail";
import { PostDetail } from "./pages/PostDetail";
import { BreakoutLog } from "./pages/BreakoutLog";

function App() {
  return (
    <SelectionProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Home />} />
            <Route path="/creators" element={<Creators />} />
            <Route path="/creators/:creatorId" element={<CreatorDetail />} />
            <Route path="/posts/:postId" element={<PostDetail />} />
            <Route path="/breakouts" element={<BreakoutLog />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SelectionProvider>
  );
}

export default App;
