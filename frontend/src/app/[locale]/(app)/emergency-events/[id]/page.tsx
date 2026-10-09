import { initRequestLocale } from "@/i18n/server";
import { EmergencyEventDetailPage } from "@/components/emergency/events";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <EmergencyEventDetailPage id={p.id} />;
}
