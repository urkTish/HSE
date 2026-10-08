import { initRequestLocale } from "@/i18n/server";
import { GasTestDetail } from "@/components/ptw/gas";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <GasTestDetail id={p.id} />;
}
