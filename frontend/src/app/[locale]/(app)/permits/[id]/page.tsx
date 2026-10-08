import { initRequestLocale } from "@/i18n/server";
import { PermitDetail } from "@/components/ptw/detail";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PermitDetail id={p.id} />;
}
