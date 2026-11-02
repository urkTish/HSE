import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MirListPage } from "@/components/quality/q2/materials";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MirListPage />;
}
