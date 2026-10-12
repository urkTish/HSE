import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { AuthorisationNewPage } from "@/components/site-vehicles/authorisations";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <AuthorisationNewPage />;
}
