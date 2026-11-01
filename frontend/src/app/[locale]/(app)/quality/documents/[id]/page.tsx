import { initRequestLocale } from "@/i18n/server";
import { DocumentDetailPage } from "@/components/quality/q4/documents";

export default async function Page({ params }: { params: Promise<{ locale: string; id: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <DocumentDetailPage id={p.id} />;
}
