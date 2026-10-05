import type { ReactNode } from "react";
// Self-hosted IBM Plex (no runtime font CDN — works on restricted site networks).
import "@fontsource-variable/ibm-plex-sans/wght.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-400.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-500.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-600.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-700.css";
import "./globals.css";

// The <html> element lives in app/[locale]/layout.tsx so lang/dir follow the URL locale.
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
