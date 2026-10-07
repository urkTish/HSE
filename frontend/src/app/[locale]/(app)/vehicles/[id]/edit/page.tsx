import { initRequestLocale } from "@/i18n/server";
import { VehicleEditPage } from "@/components/access/vehicles";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <VehicleEditPage id={p.id} />;
}
