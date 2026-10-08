import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { SuspensionLogPage } from "@/components/ptw/board";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <SuspensionLogPage />;
}
