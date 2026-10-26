import { Navigate, Route, Routes } from "react-router-dom";

import { Functional } from "@/features/Functional";
import { Load } from "@/features/Load";
import { ROUTES } from "@/shared/constants/Routes";
import { AppLayout } from "./AppNav";

/** Rotas da aplicação (HashRouter no main.tsx: URLs no formato /#/...). */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path={ROUTES.functional.path} element={<Functional />} />
        <Route path={ROUTES.load.path} element={<Load />} />
        <Route path={ROUTES.history.path} element={<div>Histórico</div>} />
        <Route path={`${ROUTES.history.path}/:batchId`} element={<div>Histórico</div>} />
      </Route>
      <Route path="*" element={<Navigate to={ROUTES.functional.path} replace />} />
    </Routes>
  );
}
