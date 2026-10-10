import { initRequestLocale } from "@/i18n/server";
import { ReportPackPage } from "@/components/scorecard/packs";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ReportPackPage id={p.id} />;
}
