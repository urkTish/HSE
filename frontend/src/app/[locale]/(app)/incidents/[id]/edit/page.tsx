import { initRequestLocale } from "@/i18n/server";
import { IncidentEditPage } from "@/components/incidents/incident-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <IncidentEditPage id={p.id} />;
}
