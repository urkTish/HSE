import { initRequestLocale } from "@/i18n/server";
import { SiteDetail } from "@/components/sites/site-detail";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string; siteId: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <SiteDetail projectId={p.id} siteId={p.siteId} />;
}
