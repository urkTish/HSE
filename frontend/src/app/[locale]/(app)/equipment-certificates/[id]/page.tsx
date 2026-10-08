import { initRequestLocale } from "@/i18n/server";
import { EqCertDetail } from "@/components/cert/eq-certs";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <EqCertDetail id={p.id} />;
}
