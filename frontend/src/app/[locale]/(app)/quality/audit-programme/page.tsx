import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ProgrammePage } from "@/components/quality/q4/audits";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ProgrammePage />;
}
