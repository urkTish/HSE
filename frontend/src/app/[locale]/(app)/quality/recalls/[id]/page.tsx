import { initRequestLocale } from "@/i18n/server";
import { RecallDetailPage } from "@/components/quality/q3/recalls";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <RecallDetailPage id={p.id} />;
}
