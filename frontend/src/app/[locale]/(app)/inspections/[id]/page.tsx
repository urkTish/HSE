import { initRequestLocale } from "@/i18n/server";
import { InspectionDetail } from "@/components/inspections/inspections";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <InspectionDetail id={p.id} />;
}
