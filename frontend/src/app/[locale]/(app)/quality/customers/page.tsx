import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CustomersPage } from "@/components/quality/q0/registers";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CustomersPage />;
}
