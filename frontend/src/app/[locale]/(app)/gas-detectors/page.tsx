import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { DetectorListPage } from "@/components/ptw/gas";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <DetectorListPage />;
}
