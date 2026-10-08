import { initRequestLocale } from "@/i18n/server";
import { PermitPrint } from "@/components/ptw/print";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PermitPrint id={p.id} />;
}
