import { initRequestLocale } from "@/i18n/server";
import { CaseDetail } from "@/components/incidents/case-detail";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <CaseDetail id={p.id} />;
}
