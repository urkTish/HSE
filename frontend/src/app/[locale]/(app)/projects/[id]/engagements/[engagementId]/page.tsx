import { initRequestLocale } from "@/i18n/server";
import { EngagementDetail } from "@/components/engagements/engagement-detail";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string; engagementId: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <EngagementDetail projectId={p.id} engagementId={p.engagementId} />;
}
