import { initRequestLocale } from "@/i18n/server";
import { TrainingReportPage } from "@/components/training/passport";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <TrainingReportPage id={decodeURIComponent(p.id)} />;
}
