import { initRequestLocale } from "@/i18n/server";
import { ItpDetailPage } from "@/components/quality/q1/itps";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ItpDetailPage id={p.id} />;
}
