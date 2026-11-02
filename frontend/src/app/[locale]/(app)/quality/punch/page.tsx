import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PunchListPage } from "@/components/quality/q1/punch";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PunchListPage />;
}
