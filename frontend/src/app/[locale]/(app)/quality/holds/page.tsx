import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HoldsListPage } from "@/components/quality/q3/holds";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <HoldsListPage />;
}
