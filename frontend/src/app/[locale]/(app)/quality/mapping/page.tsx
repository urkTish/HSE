import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MappingListPage } from "@/components/quality/q3/mapping";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MappingListPage />;
}
