import { initRequestLocale } from "@/i18n/server";
import { PerformanceSummaryPage } from "@/components/scorecard/watch";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PerformanceSummaryPage contractorId={p.id} />;
}
