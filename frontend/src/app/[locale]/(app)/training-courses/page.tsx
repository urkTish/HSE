import { initRequestLocale, type LocaleParams } from "@/i18n/server";
import { CourseListPage } from "@/components/training/courses";

export default async function Page({ params }: LocaleParams) {
  await initRequestLocale(params);
  return <CourseListPage />;
}
