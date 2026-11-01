import { initRequestLocale } from "@/i18n/server";
import { MappingDetailPage } from "@/components/quality/q3/mapping";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MappingDetailPage id={p.id} />;
}
