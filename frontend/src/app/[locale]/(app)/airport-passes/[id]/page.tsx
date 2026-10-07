import { initRequestLocale } from "@/i18n/server";
import { AirportPassDetail } from "@/components/access/passes";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <AirportPassDetail id={p.id} />;
}
