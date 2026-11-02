import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { StorageListPage } from "@/components/quality/q3/storage";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <StorageListPage />;
}
