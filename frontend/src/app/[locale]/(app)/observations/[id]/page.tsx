import { initRequestLocale } from "@/i18n/server";
import { ObservationDetail } from "@/components/observations/observations";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ObservationDetail id={p.id} />;
}
