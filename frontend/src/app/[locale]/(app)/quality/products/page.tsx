import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ProductsPage } from "@/components/quality/q3/products";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ProductsPage />;
}
