import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ReferenceListsPage } from "@/components/hse-settings/admin-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ReferenceListsPage />;
}
