import { initRequestLocale } from "@/i18n/server";
import { MrvDetailPage } from "@/components/quality/q4/audits";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MrvDetailPage id={p.id} />;
}
