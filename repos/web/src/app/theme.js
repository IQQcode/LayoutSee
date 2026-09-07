import { HostBridge } from "./HostBridge.js";

const THEME_KEY = "layoutsee.theme";

export function resolveTheme(preference, systemTheme) {
  if (preference === "dark" || preference === "light") return preference;
  return systemTheme === "dark" ? "dark" : "light";
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function initTheme(preference = "system") {
  // 首帧先用 matchMedia 同步定色，避免等宿主异步返回时闪一下
  let systemTheme = window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
  const apply = () => applyTheme(resolveTheme(preference, systemTheme));
  apply();
  HostBridge.getSystemTheme().then((theme) => {
    if (preference === "system") {
      systemTheme = theme;
      apply();
    }
  });
  // 壳走原生 nativeTheme，浏览器走 matchMedia，差异在 HostBridge 内部处理
  HostBridge.onSystemThemeChange((theme) => {
    systemTheme = theme;
    if (preference === "system") apply();
  });
  return {
    setPreference(next) {
      preference = next;
      localStorage.setItem(THEME_KEY, next);
      HostBridge.setNativeTheme?.(next);
      apply();
    },
    getPreference: () => preference,
  };
}

export function loadThemePreference() {
  return localStorage.getItem(THEME_KEY) || "system";
}
