import { initRequestLocale } from "@/i18n/server";
import { ObservationEditPage } from "@/components/observations/observation-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ObservationEditPage id={p.id} />;
}
