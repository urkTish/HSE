import { initRequestLocale } from "@/i18n/server";
import { IrDetailPage } from "@/components/quality/q1/irs";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <IrDetailPage id={p.id} />;
}
