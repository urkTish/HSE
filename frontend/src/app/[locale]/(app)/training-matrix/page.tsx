import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { MatrixPage } from "@/components/training/matrix";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <MatrixPage />;
}
