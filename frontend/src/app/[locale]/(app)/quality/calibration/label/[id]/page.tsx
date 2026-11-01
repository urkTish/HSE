import { initRequestLocale } from "@/i18n/server";
import { LabelPrintPage } from "@/components/quality/q2/calibration";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <LabelPrintPage id={p.id} />;
}
