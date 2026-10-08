import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { JsaTemplateCreatePage } from "@/components/ptw/jsa";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <JsaTemplateCreatePage />;
}
