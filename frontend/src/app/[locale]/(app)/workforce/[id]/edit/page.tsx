import { initRequestLocale } from "@/i18n/server";
import { WorkforceEditPage } from "@/components/workforce/workforce-pages";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <WorkforceEditPage id={p.id} />;
}
