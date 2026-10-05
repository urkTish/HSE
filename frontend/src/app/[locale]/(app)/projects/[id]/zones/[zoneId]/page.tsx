import { initRequestLocale } from "@/i18n/server";
import { ZoneDetail } from "@/components/zones/zone-detail";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string; zoneId: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ZoneDetail projectId={p.id} zoneId={p.zoneId} />;
}
