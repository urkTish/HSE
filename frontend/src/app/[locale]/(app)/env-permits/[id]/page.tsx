import { initRequestLocale } from "@/i18n/server";
import { EnvPermitPage } from "@/components/env/register";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <EnvPermitPage id={p.id} />;
}
