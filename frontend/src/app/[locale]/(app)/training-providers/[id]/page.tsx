import { initRequestLocale } from "@/i18n/server";
import { ProviderDetail } from "@/components/training/providers";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ProviderDetail id={decodeURIComponent(p.id)} />;
}
