import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CoveragePage } from "@/components/emergency/org";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CoveragePage />;
}
