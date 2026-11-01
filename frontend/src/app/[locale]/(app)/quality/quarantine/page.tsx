import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { QuarantineListPage } from "@/components/quality/q2/materials";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <QuarantineListPage />;
}
