import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ContractorCreate } from "@/components/contractors/contractor-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ContractorCreate />;
}
