import { initRequestLocale } from "@/i18n/server";
import { EngagementCreate } from "@/components/engagements/engagement-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <EngagementCreate projectId={p.id} />;
}
