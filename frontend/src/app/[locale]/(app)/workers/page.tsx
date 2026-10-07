import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { WorkerListPage } from "@/components/access/worker-pages";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <WorkerListPage />;
}
