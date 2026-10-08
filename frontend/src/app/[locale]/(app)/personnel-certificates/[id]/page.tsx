import { initRequestLocale } from "@/i18n/server";
import { PersonnelCertDetail } from "@/components/cert/personnel";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <PersonnelCertDetail id={p.id} />;
}
