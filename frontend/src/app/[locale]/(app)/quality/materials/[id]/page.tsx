import { initRequestLocale } from "@/i18n/server";
import { MarDetailPage } from "@/components/quality/q2/materials";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MarDetailPage id={p.id} />;
}
