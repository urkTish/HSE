import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PermitListPage } from "@/components/ptw/permits";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PermitListPage />;
}
