import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WorkerHealthLookupPage } from "@/components/medical/worker";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WorkerHealthLookupPage />;
}
