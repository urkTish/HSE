import { initRequestLocale } from "@/i18n/server";
import { HeatLogEntryPage } from "@/components/heat/log";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <HeatLogEntryPage id={decodeURIComponent(p.id)} />;
}
