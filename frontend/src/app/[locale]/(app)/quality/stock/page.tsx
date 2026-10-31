import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { StockPage } from "@/components/quality/q3/stock";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <StockPage />;
}
