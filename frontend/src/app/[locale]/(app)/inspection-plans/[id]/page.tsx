import { initRequestLocale } from "@/i18n/server";
import { PlanDetail } from "@/components/inspections/inspections";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PlanDetail id={p.id} />;
}
