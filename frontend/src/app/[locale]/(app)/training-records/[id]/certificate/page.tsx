import { initRequestLocale } from "@/i18n/server";
import { CertificatePrintPage } from "@/components/training/records";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <CertificatePrintPage id={decodeURIComponent(p.id)} />;
}
