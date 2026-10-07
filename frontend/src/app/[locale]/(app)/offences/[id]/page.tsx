import { initRequestLocale } from "@/i18n/server";
import { OffenceDetail } from "@/components/access/adps";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <OffenceDetail id={p.id} />;
}
