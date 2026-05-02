import { Outlet } from "react-router-dom";
import { TopNavigation } from "./TopNavigation";

export function AppShell() {
  return (
    <div className="h-screen grid grid-rows-[64px_minmax(0,1fr)] bg-surface-canvas">
      <TopNavigation />
      <Outlet />
    </div>
  );
}
