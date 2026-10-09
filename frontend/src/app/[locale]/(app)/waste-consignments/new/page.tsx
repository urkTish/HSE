import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { NewConsignmentPage } from "@/components/env/waste";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <NewConsignmentPage />;
}
