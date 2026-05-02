import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/layouts/AppShell";
import { TradePage } from "@/pages/trade/TradePage";
import { ViewPage } from "@/pages/view/ViewPage";
import { EditPage } from "@/pages/edit/EditPage";
import { ManagePage } from "@/pages/manage/ManagePage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <TradePage /> },
      { path: "trade", element: <TradePage /> },
      { path: "view", element: <ViewPage /> },
      { path: "edit", element: <EditPage /> },
      { path: "manage", element: <ManagePage /> }
    ]
  }
]);
