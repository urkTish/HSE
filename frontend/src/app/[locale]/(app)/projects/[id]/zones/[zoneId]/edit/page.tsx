import { initRequestLocale } from "@/i18n/server";
import { ZoneEdit } from "@/components/zones/zone-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string; zoneId: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ZoneEdit projectId={p.id} zoneId={p.zoneId} />;
}
