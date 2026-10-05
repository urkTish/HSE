/** Colour theme preference: "system" follows the OS; stored per device (a viewer convenience, not account data). */
export type ThemePreference = "light" | "dark" | "system";
export const THEME_STORAGE_KEY = "hse.theme";
const THEME_EVENT = "hse-theme-change";

/** For useSyncExternalStore: the current preference as applied to <html>. */
export function subscribeTheme(cb: () => void): () => void {
  window.addEventListener(THEME_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(THEME_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}
export function themeSnapshot(): ThemePreference {
  const v = document.documentElement.getAttribute("data-theme");
  return v === "light" || v === "dark" ? v : "system";
}

export function applyTheme(pref: ThemePreference): void {
  const root = document.documentElement;
  if (pref === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", pref);
  window.dispatchEvent(new Event(THEME_EVENT));
  try {
    if (pref === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    /* storage blocked: the choice lasts for this page only */
  }
}

/** Inline in <head> so the stored theme applies before first paint (no light flash in dark mode). */
export const THEME_BOOT_SCRIPT = `try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;
