import { initRequestLocale } from "@/i18n/server";
import { DrillDetailPage } from "@/components/emergency/drills";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <DrillDetailPage id={p.id} />;
}
