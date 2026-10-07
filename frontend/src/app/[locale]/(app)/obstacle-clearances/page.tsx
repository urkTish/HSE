import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { ObstacleListPage } from "@/components/access/works";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <ObstacleListPage />;
}
