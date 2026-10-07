import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PassApplicationCreatePage } from "@/components/access/passes";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PassApplicationCreatePage />;
}
