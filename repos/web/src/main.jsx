import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppShell } from "./app/AppShell.jsx";
import { GlobalErrorBoundary } from "./app/GlobalErrorBoundary.jsx";
import { wireLogging } from "./app/LoggingBridge.js";
import { HostBridge } from "./app/HostBridge.js";
import { initTheme, loadThemePreference } from "./app/theme.js";
import { ToastProvider } from "./components/ui.jsx";
import { DevicesPage } from "./features/devices/DevicesPage.jsx";
import { GroupPreviewPage } from "./features/group-preview/GroupPreviewPage.jsx";
import { SettingsPage } from "./features/settings/SettingsPage.jsx";
import { WorkbenchPage } from "./features/workbench/WorkbenchPage.jsx";
import "./styles/tokens.css";
import "./styles/app.css";

function App() {
  const [themeController] = useState(() => {
    wireLogging();
    return initTheme(loadThemePreference());
  });
  useEffect(() => {
    HostBridge.init();
  }, []);

  return (
    <GlobalErrorBoundary>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/devices" replace />} />
            <Route element={<AppShell />}>
              <Route path="/devices" element={<DevicesPage />} />
              <Route path="/group" element={<GroupPreviewPage />} />
              <Route path="/settings" element={<SettingsPage onThemeChange={(theme) => themeController.setPreference(theme)} />} />
            </Route>
            <Route path="/devices/:deviceId/workbench/:tab" element={<WorkbenchPage />} />
            <Route path="*" element={<Navigate to="/devices" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </GlobalErrorBoundary>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
