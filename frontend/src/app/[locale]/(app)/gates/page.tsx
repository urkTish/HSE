import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { GateListPage } from "@/components/access/gates";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <GateListPage />;
}
