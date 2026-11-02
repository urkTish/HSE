import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ComplaintListPage } from "@/components/quality/q0/records";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ComplaintListPage />;
}
