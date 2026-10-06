import { initRequestLocale } from "@/i18n/server";
import { WorkforceImportReportRoute } from "@/components/workforce/workforce-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <WorkforceImportReportRoute id={p.id} />;
}
