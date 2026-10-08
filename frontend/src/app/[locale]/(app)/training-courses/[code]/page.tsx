import { initRequestLocale } from "@/i18n/server";
import { CourseDetail } from "@/components/training/courses";

export default async function Page({ params }: { params: Promise<{ locale: string; code: string }> }) {
  await initRequestLocale(params);
  const p = await params;
  return <CourseDetail code={decodeURIComponent(p.code)} />;
}
