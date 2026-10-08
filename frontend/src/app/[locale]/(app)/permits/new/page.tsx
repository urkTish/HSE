import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PermitCreatePage } from "@/components/ptw/permits";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PermitCreatePage />;
}
