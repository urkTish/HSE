import { initRequestLocale } from "@/i18n/server";
import { MteDetailPage } from "@/components/quality/q0/registers";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MteDetailPage id={p.id} />;
}
