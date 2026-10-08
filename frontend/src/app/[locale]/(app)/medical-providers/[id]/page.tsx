import { initRequestLocale } from "@/i18n/server";
import { MedicalProviderDetail } from "@/components/medical/catalogue";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <MedicalProviderDetail id={decodeURIComponent(p.id)} />;
}
