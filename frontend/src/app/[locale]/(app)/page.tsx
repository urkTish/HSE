import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HomePage as Home } from "@/components/home/home-page";

export default async function HomePage({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <Home />;
}
