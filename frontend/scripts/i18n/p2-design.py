# Phase 2 design pass (UI/UX): presentation-only strings. New keys only (later p2-* files must not be overridden).
P = {
  "gate": {
    "withNote": ["With a note — see below", "مع ملاحظة — انظر أدناه"],
    "reasonDeny": ["Reason for refusal", "سبب الرفض"],
    "reasonWarn": ["Warning", "تنبيه"],
    "reasonNote": ["Note", "ملاحظة"],
  },
}

# Print views (access card, AVP sticker, WAP): every value holds "EN|AR"; the print shows both languages.
_BI = {
  "cardTitle": "Site access card|بطاقة دخول الموقع",
  "stickerTitle": "Airside vehicle permit|تصريح مركبة الجانب الجوي",
  "wapTitle": "Work-area permit|تصريح منطقة عمل",
  "project": "Project|المشروع",
  "status": "Status|الحالة",
  "site": "Site|الموقع",
  "zones": "Zones|المناطق",
  "contractor": "Contractor|المقاول",
  "dates": "Valid dates|مدة الصلاحية",
  "windows": "Work windows|نوافذ العمل",
  "scope": "Scope|النطاق",
  "crew": "Crew|الطاقم",
  "workerNo": "Worker no.|رقم العامل",
  "name": "Name|الاسم",
  "role": "Role|الدور",
  "vehicles": "Vehicles|المركبات",
  "avpNo": "AVP no.|رقم التصريح",
  "stickerNo": "Sticker no.|رقم الملصق",
  "vehicleNo": "Vehicle no.|رقم المركبة",
  "fleetNo": "Fleet no.|رقم الأسطول",
  "areas": "Areas|المناطق المسموحة",
  "issued": "Issued|تاريخ الإصدار",
  "printedRef": "Printed ref|الرقم المطبوع",
  "scanAtGate": "Scan at the gate|امسح عند البوابة",
  "wapFooter": "Display at the work site. Valid only within the stated windows and while not suspended.|يُعرض في موقع العمل. صالح ضمن النوافذ المحددة فقط وما لم يكن موقوفاً.",
}
P["accessPrint"] = {k: [v, v] for k, v in _BI.items()}
