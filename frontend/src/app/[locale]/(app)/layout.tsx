import type { ReactNode } from "react";
import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AppFrame } from "@/components/shell/app-frame";

export default async function AppLayout({ children, params }: { children: ReactNode } & LocaleParams) {
  await initRequestLocale(params);
  return <AppFrame>{children}</AppFrame>;
}
