import { initRequestLocale } from "@/i18n/server";
import { WorkerDetail } from "@/components/access/workers";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <WorkerDetail id={p.id} />;
}
