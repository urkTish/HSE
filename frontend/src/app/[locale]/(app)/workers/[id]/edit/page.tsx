import { initRequestLocale } from "@/i18n/server";
import { WorkerEditPage } from "@/components/access/worker-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <WorkerEditPage id={p.id} />;
}
