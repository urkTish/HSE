import { initRequestLocale } from "@/i18n/server";
import { EquipmentDetail } from "@/components/cert/equipment";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <EquipmentDetail id={p.id} />;
}
