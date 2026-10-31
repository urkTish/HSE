import { initRequestLocale } from "@/i18n/server";
import { DossierDetailPage } from "@/components/quality/q1/dossiers";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <DossierDetailPage id={p.id} />;
}
