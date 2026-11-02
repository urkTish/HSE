import { initRequestLocale } from "@/i18n/server";
import { ReceiptDetailPage } from "@/components/quality/q3/receiving";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ReceiptDetailPage id={p.id} />;
}
