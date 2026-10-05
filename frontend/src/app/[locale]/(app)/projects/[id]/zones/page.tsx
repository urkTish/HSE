import { initRequestLocale } from "@/i18n/server";
import { ZoneList } from "@/components/zones/zone-list";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ZoneList projectId={p.id} />;
}
