import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
      <div className="font-mono text-5xl text-slate-700">404</div>
      <h1 className="text-lg font-semibold text-white">This route is not on the map</h1>
      <p className="max-w-sm text-xs text-fog">
        The page you asked for does not exist. Head back to the workspace and start a run.
      </p>
      <Link to="/" className="btn-primary mt-2">
        Open workspace
      </Link>
    </div>
  );
}