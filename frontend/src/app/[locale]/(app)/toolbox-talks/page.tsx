import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ToolboxTalksPage } from "@/components/field/talks";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ToolboxTalksPage />;
}
