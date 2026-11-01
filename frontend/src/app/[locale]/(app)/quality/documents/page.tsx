import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { DocumentsPage } from "@/components/quality/q4/documents";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <DocumentsPage />;
}
