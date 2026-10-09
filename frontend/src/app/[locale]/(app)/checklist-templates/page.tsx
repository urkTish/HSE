import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { TemplatesPage } from "@/components/field/library";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <TemplatesPage />;
}
