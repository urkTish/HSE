import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ReturnsListPage } from "@/components/quality/q3/returns";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ReturnsListPage />;
}
