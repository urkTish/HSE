import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ReadingsPage } from "@/components/quality/q3/storage";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ReadingsPage />;
}
