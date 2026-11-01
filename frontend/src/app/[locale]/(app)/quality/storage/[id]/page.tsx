import { initRequestLocale } from "@/i18n/server";
import { ZoneDetailPage } from "@/components/quality/q3/storage";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ZoneDetailPage id={p.id} />;
}
