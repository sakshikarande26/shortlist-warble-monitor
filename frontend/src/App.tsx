import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/ui/AppShell";
import { SelectionProvider } from "./lib/selection";
import { AgentChatProvider } from "./lib/agentChat";
import { Home } from "./pages/Home";
import { Creators } from "./pages/Creators";
import { CreatorDetail } from "./pages/CreatorDetail";
import { PostDetail } from "./pages/PostDetail";
import { PostsBoard } from "./pages/PostsBoard";
import { BreakoutLog } from "./pages/BreakoutLog";
import { UnavailablePosts } from "./pages/UnavailablePosts";
import { Status } from "./pages/Status";

function App() {
  return (
    <SelectionProvider>
      <AgentChatProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Home />} />
            <Route path="/creators" element={<Creators />} />
            <Route path="/creators/:creatorId" element={<CreatorDetail />} />
            <Route path="/posts" element={<PostsBoard />} />
            <Route path="/posts/:postId" element={<PostDetail />} />
            <Route path="/breakouts" element={<BreakoutLog />} />
            <Route path="/unavailable" element={<UnavailablePosts />} />
            <Route path="/status" element={<Status />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </AgentChatProvider>
    </SelectionProvider>
  );
}

export default App;
