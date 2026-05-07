import { Outlet } from "react-router-dom";
import { TopNavigation } from "./TopNavigation";

export function AppShell() {
  return (
    <div className="h-screen grid grid-rows-[64px_minmax(0,1fr)] bg-surface-canvas overflow-hidden">
      <TopNavigation />
      <div className="min-h-0 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
