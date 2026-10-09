import { initRequestLocale } from "@/i18n/server";
import { ErpDetailPage } from "@/components/emergency/plan";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ErpDetailPage id={p.id} />;
}
