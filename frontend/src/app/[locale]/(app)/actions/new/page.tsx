import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CaCreatePage } from "@/components/actions/ca-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CaCreatePage />;
}
