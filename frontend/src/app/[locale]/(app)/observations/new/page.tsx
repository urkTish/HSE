import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ObservationCreatePage } from "@/components/observations/observation-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ObservationCreatePage />;
}
