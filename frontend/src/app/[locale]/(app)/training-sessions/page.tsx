import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { SessionListPage } from "@/components/training/sessions";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <SessionListPage />;
}
