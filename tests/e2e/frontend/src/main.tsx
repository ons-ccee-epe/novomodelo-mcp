import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { Theme } from "@radix-ui/themes";
import "@radix-ui/themes/styles.css";

import { AppRoutes } from "@/navigation";
import { ErrorBoundary } from "@/shared/ErrorBoundary";
import { applyInitialColorScheme } from "@/theme/colorScheme";
import "@/theme/styles.css";

applyInitialColorScheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* HashRouter: hospedagem estática, sem rewrite de SPA (URLs /#/...) */}
    <HashRouter>
      <Theme accentColor="orange" grayColor="slate" radius="medium">
        <ErrorBoundary>
          <AppRoutes />
        </ErrorBoundary>
      </Theme>
    </HashRouter>
  </StrictMode>,
);
