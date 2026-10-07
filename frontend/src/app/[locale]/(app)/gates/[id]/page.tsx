import { initRequestLocale } from "@/i18n/server";
import { GateDetail } from "@/components/access/gates";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <GateDetail id={p.id} />;
}
