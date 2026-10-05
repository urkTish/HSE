import { initRequestLocale } from "@/i18n/server";
import { SiteEdit } from "@/components/sites/site-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string; siteId: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <SiteEdit projectId={p.id} siteId={p.siteId} />;
}
