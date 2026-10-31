import { initRequestLocale } from "@/i18n/server";
import { TripDetailPage } from "@/components/quality/q3/transport";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <TripDetailPage id={p.id} />;
}
