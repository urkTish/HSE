import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CourseCreatePage } from "@/components/access/inductions";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CourseCreatePage />;
}
