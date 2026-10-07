import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WorkerCreatePage } from "@/components/access/worker-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WorkerCreatePage />;
}
