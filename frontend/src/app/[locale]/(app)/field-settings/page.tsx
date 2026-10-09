import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { FieldSettingsPage } from "@/components/field/overview";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <FieldSettingsPage />;
}
