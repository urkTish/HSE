import { initRequestLocale } from "@/i18n/server";
import { FieldAuditPage } from "@/components/field/audits";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <FieldAuditPage id={p.id} />;
}
