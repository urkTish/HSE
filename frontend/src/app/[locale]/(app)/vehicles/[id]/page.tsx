import { initRequestLocale } from "@/i18n/server";
import { VehicleDetail } from "@/components/access/vehicles";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <VehicleDetail id={p.id} />;
}
