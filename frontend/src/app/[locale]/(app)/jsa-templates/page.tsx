import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { JsaTemplatesPage } from "@/components/ptw/jsa";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <JsaTemplatesPage />;
}
