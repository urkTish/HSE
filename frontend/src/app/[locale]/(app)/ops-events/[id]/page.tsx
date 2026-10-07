import { initRequestLocale } from "@/i18n/server";
import { OpsEventDetail } from "@/components/access/waps";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <OpsEventDetail id={p.id} />;
}
