import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { DrillProgrammePage } from "@/components/emergency/drills";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <DrillProgrammePage />;
}
