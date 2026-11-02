import type { routing } from "@/i18n/routing";
import type messages from "../messages/en.json";
import type q0 from "../messages/quality/q0.en.json";
import type q1 from "../messages/quality/q1.en.json";
import type q2 from "../messages/quality/q2.en.json";
import type q3 from "../messages/quality/q3.en.json";
import type q4 from "../messages/quality/q4.en.json";

declare module "next-intl" {
  interface AppConfig {
    Locale: (typeof routing.locales)[number];
    // 8-quality §3.3a: the Quality parts' files are merged under `quality` (src/i18n/request.ts)
    Messages: typeof messages & { quality: typeof q0 & typeof q1 & typeof q2 & typeof q3 & typeof q4 };
  }
}
