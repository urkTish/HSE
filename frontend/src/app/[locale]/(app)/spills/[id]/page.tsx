import { initRequestLocale } from "@/i18n/server";
import { SpillPage } from "@/components/env/spills";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <SpillPage id={p.id} />;
}
