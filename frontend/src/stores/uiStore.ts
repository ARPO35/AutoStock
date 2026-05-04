import { create } from "zustand";
import type { RouteKey } from "@/types";

const viewTabs = ["总览", "账号详情", "交易历史", "资产曲线", "股票信息", "决策日志", "时间线控制"];
const editTabs = ["账户信息", "余额修改", "持仓修改", "订单修正", "会话绑定"];
const manageSections = ["模型与API", "提示词", "Skills", "Tools", "触发器", "数据管理", "系统设置"];

interface UIState {
  route: RouteKey;
  viewTab: string;
  editTab: string;
  manageSection: string;
  selectedTool: string | null;
  leftCollapsed: boolean;
  inspectorWidth: number;
  error: string | null;

  setRoute: (route: RouteKey) => void;
  setViewTab: (tab: string) => void;
  setEditTab: (tab: string) => void;
  setManageSection: (section: string) => void;
  setSelectedTool: (tool: string | null) => void;
  setLeftCollapsed: (value: boolean) => void;
  setInspectorWidth: (value: number) => void;
  setError: (error: string | null) => void;
}

function routeFromPath(pathname: string): RouteKey {
  const first = pathname.split("/").filter(Boolean)[0];
  return first === "view" || first === "edit" || first === "manage" ? first : "trade";
}

export const useUIStore = create<UIState>((set) => ({
  route: routeFromPath(window.location.pathname),
  viewTab: viewTabs[0],
  editTab: editTabs[0],
  manageSection: manageSections[0],
  selectedTool: null,
  leftCollapsed: false,
  inspectorWidth: (() => {
    const stored = Number(window.localStorage.getItem("autostock.inspectorWidth"));
    return Number.isFinite(stored) && stored >= 420 ? stored : 460;
  })(),
  error: null,

  setRoute: (route) => set({ route }),
  setViewTab: (viewTab) => set({ viewTab }),
  setEditTab: (editTab) => set({ editTab }),
  setManageSection: (manageSection) => set({ manageSection }),
  setSelectedTool: (selectedTool) => set({ selectedTool }),
  setLeftCollapsed: (leftCollapsed) => set({ leftCollapsed }),
  setInspectorWidth: (value) => {
    set({ inspectorWidth: value });
    window.localStorage.setItem("autostock.inspectorWidth", String(value));
  },
  setError: (error) => set({ error })
}));

export { viewTabs, editTabs, manageSections };
