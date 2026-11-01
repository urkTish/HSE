import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WeldingPage } from "@/components/quality/q2/welding";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WeldingPage />;
}
