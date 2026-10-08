import { initRequestLocale } from "@/i18n/server";
import { PtwAuditDetail } from "@/components/ptw/audits";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PtwAuditDetail id={p.id} />;
}
