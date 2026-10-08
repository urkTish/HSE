import { initRequestLocale } from "@/i18n/server";
import { TpiDetail } from "@/components/cert/tpis";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <TpiDetail id={p.id} />;
}
