import { Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import Agents from "./pages/Agents";
import Compare from "./pages/Compare";
import Docs from "./pages/Docs";
import NotFound from "./pages/NotFound";
import RunDetail from "./pages/RunDetail";
import Runs from "./pages/Runs";
import Scenarios from "./pages/Scenarios";
import Workspace from "./pages/Workspace";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Workspace />} />
        <Route path="scenarios" element={<Scenarios />} />
        <Route path="agents" element={<Agents />} />
        <Route path="runs" element={<Runs />} />
        <Route path="runs/:runId" element={<RunDetail />} />
        <Route path="compare" element={<Compare />} />
        <Route path="docs" element={<Docs />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}