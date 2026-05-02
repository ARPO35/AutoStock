import { RouterProvider } from "react-router-dom";
import { useEffect } from "react";
import { router } from "@/app/routes";
import { useDataStore } from "@/stores/dataStore";
import { useMarketStore } from "@/stores/marketStore";
import { useUIStore } from "@/stores/uiStore";
import { AlertTriangle } from "lucide-react";

export function App() {
  const loadAll = useDataStore((s) => s.loadAll);
  const loadDataState = useMarketStore((s) => s.loadDataState);
  const error = useUIStore((s) => s.error);

  useEffect(() => {
    loadAll().catch(() => {});
    loadDataState().catch(() => {});
  }, []);

  return (
    <>
      {error && (
        <div className="fixed z-50 top-[76px] left-1/2 -translate-x-1/2 inline-flex items-center gap-2 max-w-[720px] px-3.5 py-2.5 border border-trading-rise/40 rounded-lg bg-trading-rise/10 text-trading-rise text-sm">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}
      <RouterProvider router={router} />
    </>
  );
}
