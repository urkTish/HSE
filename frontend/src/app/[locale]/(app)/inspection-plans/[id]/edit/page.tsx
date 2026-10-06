import { initRequestLocale } from "@/i18n/server";
import { PlanEditPage } from "@/components/inspections/inspection-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PlanEditPage id={p.id} />;
}
