import { initRequestLocale } from "@/i18n/server";
import { ReportDetail } from "@/components/reports/monthly-reports";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ReportDetail id={p.id} />;
}
