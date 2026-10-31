import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { NcrNewPage } from "@/components/quality/q0/ncrs";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <NcrNewPage />;
}
