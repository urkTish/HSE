import { initRequestLocale } from "@/i18n/server";
import { SiteList } from "@/components/sites/site-list";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <SiteList projectId={p.id} />;
}
