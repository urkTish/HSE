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

/**
 * Surface preference (D-277): "glass" = frosted surfaces over the emerald mesh, "solid" = flat surfaces,
 * "auto" = glass on a fine pointer and solid on a coarse one (phones and gate tablets in sunlight), decided
 * in CSS (`@media (pointer: coarse)` in styles/tokens.css). Stored per device like the theme.
 */
export type SurfacePreference = "glass" | "solid" | "auto";
export const SURFACE_STORAGE_KEY = "hse.surface";
const SURFACE_EVENT = "hse-surface-change";

export function subscribeSurface(cb: () => void): () => void {
  window.addEventListener(SURFACE_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(SURFACE_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}
export function surfaceSnapshot(): SurfacePreference {
  const v = document.documentElement.getAttribute("data-surface");
  return v === "glass" || v === "solid" ? v : "auto";
}
export function applySurface(pref: SurfacePreference): void {
  const root = document.documentElement;
  if (pref === "auto") root.removeAttribute("data-surface");
  else root.setAttribute("data-surface", pref);
  window.dispatchEvent(new Event(SURFACE_EVENT));
  try {
    if (pref === "auto") window.localStorage.removeItem(SURFACE_STORAGE_KEY);
    else window.localStorage.setItem(SURFACE_STORAGE_KEY, pref);
  } catch {
    /* storage blocked: the choice lasts for this page only */
  }
}

/** Inline in <head> so the stored theme and surface apply before first paint (no light flash in dark mode). */
export const THEME_BOOT_SCRIPT = `try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t);var s=localStorage.getItem("${SURFACE_STORAGE_KEY}");if(s==="glass"||s==="solid")document.documentElement.setAttribute("data-surface",s)}catch(e){}`;
