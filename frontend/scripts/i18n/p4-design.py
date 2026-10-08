# Phase 4 design pass (UI/UX): presentation-only strings for the certification screens. New keys only,
# plus the equipment-sticker "Tag" label, whose Arabic read "card" (البطاقة) instead of the equipment tag (الوسم).
P = {
  "certDesign": {
    "stateLabel": ["Certification state", "حالة الاعتماد"],
    "doNotUse": ["Do not use", "ممنوع الاستخدام"],
    "eq": {
      "inServiceOk": ["In service — certificate in force", "في الخدمة — الشهادة سارية"],
      "inServiceOkLine": ["Certified for use. Today's checks on site (sticker, arrival inspection, defects) are on its project page.", "معتمدة للاستخدام. فحوص اليوم في الموقع (الملصق وفحص الوصول والعيوب) في صفحتها على المشروع."],
      "noCert": ["No certificate in force", "لا توجد شهادة سارية"],
      "noCertLine": ["Do not use for certified work until a valid certificate line is accepted.", "لا تُستخدم في الأعمال التي تتطلب اعتماداً حتى تُقبل شهادة سارية."],
      "awaitingLine": ["Not usable until a certificate is accepted.", "غير قابلة للاستخدام حتى تُقبل شهادة."],
      "retiredLine": ["Retired. No longer used on any project.", "خارج الخدمة نهائياً. لا تُستخدم في أي مشروع."],
      "onProject": ["Today on {ref}", "اليوم في {ref}"],
    },
    "dep": {
      "usable": ["Usable on this project today", "قابلة للاستخدام في هذا المشروع اليوم"],
      "usableLine": ["Today's checks for this item pass.", "فحوص اليوم لهذه المعدة ناجحة."],
      "notUsable": ["Do not use on this project today", "ممنوع استخدامها في هذا المشروع اليوم"],
      "plannedLine": ["Not on site yet. Usable only after arrival and its checks.", "لم تصل إلى الموقع بعد. لا تُستخدم إلا بعد الوصول وفحوصه."],
      "endedLine": ["No longer deployed on this project.", "لم تعد معيّنة في هذا المشروع."],
    },
    "pc": {
      "inForceLine": ["Valid for the scope, capacity and limitations shown on this page.", "سارية للنطاق والسعة والقيود المبينة في هذه الصفحة."],
      "notInForceLine": ["The holder may not do work that needs this card.", "لا يجوز لحاملها أداء عمل يتطلب هذه البطاقة."],
      "pendingLine": ["Not in force until it is reviewed and accepted.", "غير سارية حتى تُراجع وتُقبل."],
    },
    "sc": {
      "usableRestricted": ["Usable today — with restrictions", "قابلة للاستخدام اليوم — بقيود"],
      "restrictedLine": ["Yellow tag: use only as the restrictions below allow.", "بطاقة صفراء: لا تُستخدم إلا وفق القيود أدناه."],
      "usableLine": ["Green tag: safe to use within its load class.", "بطاقة خضراء: آمنة للاستخدام ضمن فئة الحمل."],
      "notUsableLine": ["Do not access or load this scaffold.", "لا تصعد على هذه السقالة ولا تحمّلها."],
    },
    "tag": {
      "expired": ["Tag expired — do not use", "البطاقة منتهية — ممنوع الاستخدام"],
      "inspection_required": ["Inspection required — do not use", "تتطلب فحصاً — ممنوع الاستخدام"],
    },
    "zoneDoNotUse": ["{n} do not use", "{n} ممنوع الاستخدام"],
    "zoneRestricted": ["{n} with restrictions", "{n} بقيود"],
    "zoneGreen": ["{n} green", "{n} خضراء"],
    "historyUnavailable": ["Change history is not available for this record yet.", "سجل التغييرات غير متاح لهذا السجل بعد."],
    "reqHook": {
      "equipment_certificate": ["Equipment certificate", "شهادة المعدة"],
      "personnel_certificate": ["Personnel certificate", "شهادة الأفراد"],
      "training_course": ["Training course", "دورة تدريبية"],
      "medical_fitness": ["Medical fitness", "اللياقة الطبية"],
    },
    "stopGroup": ["Stop use", "إيقاف الاستخدام"],
    "irreversible": ["This cannot be undone. Check the equipment number before you confirm.", "لا يمكن التراجع عن هذا الإجراء. تحقق من رقم المعدة قبل التأكيد."],
    "restrictions": ["Restrictions", "القيود"],
  },
}

# Sticker category labels in both languages ("EN|AR"), built from the existing enum messages (presentation only).
import json as _json
import os as _os

_M = _os.path.join(_os.path.dirname(__file__), "..", "..", "messages")
with open(_os.path.join(_M, "en.json"), encoding="utf-8") as _f:
    _EN = _json.load(_f)["enums"]
with open(_os.path.join(_M, "ar.json"), encoding="utf-8") as _f:
    _AR = _json.load(_f)["enums"]
P["certBi"] = {"eqc": {_k: [f"{_v}|{_AR['eqc'][_k]}", f"{_v}|{_AR['eqc'][_k]}"] for _k, _v in _EN["eqc"].items()}}
P["accessPrint"] = {"eqTag": ["Tag|الوسم", "Tag|الوسم"]}
