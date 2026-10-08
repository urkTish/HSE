import { initRequestLocale } from "@/i18n/server";
import { AssessmentDetail } from "@/components/medical/assessments";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <AssessmentDetail id={decodeURIComponent(p.id)} />;
}
