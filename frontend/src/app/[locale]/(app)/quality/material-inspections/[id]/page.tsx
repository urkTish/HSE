import { initRequestLocale } from "@/i18n/server";
import { MirDetailPage } from "@/components/quality/q2/materials";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MirDetailPage id={p.id} />;
}
