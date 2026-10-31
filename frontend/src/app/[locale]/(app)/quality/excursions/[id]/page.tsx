import { initRequestLocale } from "@/i18n/server";
import { ExcursionDetailPage } from "@/components/quality/q3/excursions";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ExcursionDetailPage id={p.id} />;
}
