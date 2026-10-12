import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { PreUseCheckNewPage } from "@/components/site-vehicles/checks";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <PreUseCheckNewPage />;
}
