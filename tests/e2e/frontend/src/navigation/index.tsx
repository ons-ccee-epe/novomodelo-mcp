import { Navigate, Route, Routes } from "react-router-dom";

import { Dashboard } from "@/features/Dashboard";
import { Load } from "@/features/Load";
import { ROUTES } from "@/shared/constants/Routes";
import { AppLayout } from "./AppNav";

/** Rotas da aplicação (HashRouter no main.tsx: URLs no formato /#/...). */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path={ROUTES.dashboard.path} element={<Dashboard />} />
        <Route path={ROUTES.load.path} element={<Load />} />
      </Route>
      <Route path="*" element={<Navigate to={ROUTES.dashboard.path} replace />} />
    </Routes>
  );
}
