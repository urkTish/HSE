import { initRequestLocale } from "@/i18n/server";
import { CertImportDetail } from "@/components/cert/imports";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <CertImportDetail id={p.id} />;
}
