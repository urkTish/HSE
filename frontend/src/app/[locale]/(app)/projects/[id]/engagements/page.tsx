import { initRequestLocale } from "@/i18n/server";
import { EngagementList } from "@/components/engagements/engagement-list";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <EngagementList projectId={p.id} />;
}
