import { initRequestLocale } from "@/i18n/server";
import { ConsignmentPage } from "@/components/env/waste";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <ConsignmentPage id={p.id} />;
}
