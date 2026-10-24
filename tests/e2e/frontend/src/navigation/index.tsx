import { Navigate, Route, Routes } from "react-router-dom";

import { Dashboard } from "@/features/Dashboard";
import { ROUTES } from "@/shared/constants/Routes";

/** Rotas da aplicação (HashRouter no main.tsx: URLs no formato /#/...). */
export function AppRoutes() {
  return (
    <Routes>
      <Route path={ROUTES.dashboard.path} element={<Dashboard />} />
      <Route path="*" element={<Navigate to={ROUTES.dashboard.path} replace />} />
    </Routes>
  );
}
