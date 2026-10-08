import { initRequestLocale } from "@/i18n/server";
import { WorkerHealthPage } from "@/components/medical/worker";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <WorkerHealthPage deploymentId={decodeURIComponent(p.id)} />;
}
