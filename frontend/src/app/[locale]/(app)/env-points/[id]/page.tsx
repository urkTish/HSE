import { initRequestLocale } from "@/i18n/server";
import { EnvPointPage } from "@/components/env/monitoring";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <EnvPointPage id={p.id} />;
}
