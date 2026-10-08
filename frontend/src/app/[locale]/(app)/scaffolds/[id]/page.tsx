import { initRequestLocale } from "@/i18n/server";
import { ScaffoldDetail } from "@/components/cert/scaffolds";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ScaffoldDetail id={p.id} />;
}
