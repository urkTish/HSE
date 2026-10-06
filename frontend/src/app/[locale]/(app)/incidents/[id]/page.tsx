import { initRequestLocale } from "@/i18n/server";
import { IncidentDetail } from "@/components/incidents/incident-detail";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <IncidentDetail id={p.id} />;
}
