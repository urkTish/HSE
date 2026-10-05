import { initRequestLocale } from "@/i18n/server";
import { EngagementEdit } from "@/components/engagements/engagement-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string; engagementId: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <EngagementEdit projectId={p.id} engagementId={p.engagementId} />;
}
