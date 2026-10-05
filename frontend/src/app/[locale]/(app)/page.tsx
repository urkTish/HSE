import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { HomePlaceholder } from "@/components/home/home-placeholder";

export default async function HomePage({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <HomePlaceholder />;
}
