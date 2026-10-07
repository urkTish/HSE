import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WapListPage } from "@/components/access/waps";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WapListPage />;
}
