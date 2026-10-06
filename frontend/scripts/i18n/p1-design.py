# Phase 1 design pass (UI/UX): presentation-only strings.
P = {
  "dashboard": {
    "daysLeft": ["{n, plural, one {{days} day left} other {{days} days left}}", "متبقٍ {days} يوم"],
    "showAll": ["Show all ({count})", "عرض الكل ({count})"],
    "showLess": ["Show fewer", "عرض أقل"],
    "refreshInsights": ["Refresh insights", "تحديث الرؤى"],
    "needsToday": ["What needs you today", "ما يتطلب متابعتك اليوم"],
  },
  "reports": {
    # Print header/footer: each value holds both languages ("EN|AR"); the print view shows both sides.
    "printDoc": {
      "title": ['Monthly HSE report|التقرير الشهري للصحة والسلامة والبيئة', 'Monthly HSE report|التقرير الشهري للصحة والسلامة والبيئة'],
      "project": ['Project|المشروع', 'Project|المشروع'],
      "month": ['Reporting month|شهر التقرير', 'Reporting month|شهر التقرير'],
      "status": ['Status|الحالة', 'Status|الحالة'],
      "generated": ['Drafted|تاريخ الإعداد', 'Drafted|تاريخ الإعداد'],
      "published": ['Published|تاريخ النشر', 'Published|تاريخ النشر'],
      "hash": ['Figures hash|بصمة الأرقام', 'Figures hash|بصمة الأرقام'],
      "confidential": ['Confidential: for client and authority submission|سري: للتقديم إلى العميل والجهات المختصة', 'Confidential: for client and authority submission|سري: للتقديم إلى العميل والجهات المختصة'],
    },
  },
}
P["imports"] = {"noImports": ["No imports yet.", "لا توجد عمليات استيراد بعد."]}
