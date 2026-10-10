# Phase 6f design pass (UI/UX): presentation-only strings for the incident follow-up screens (incident panel,
# notifications register, packs, lessons, acknowledgements, effectiveness checks, rules).
# New keys only (fuDesign.*); no earlier string is changed.
P = {
    "fuDesign": {
        "spanD": ["{d} d", "{d} يوم"],
        "endOfDay": ["by 23:59 Riyadh time, end of that day", "حتى 23:59 بتوقيت الرياض، نهاية ذلك اليوم"],
        "endOfDayShort": ["end of day", "نهاية اليوم"],
        "deadlineRule": [
            "Times are Riyadh time. A date-only deadline runs to 23:59 of that day.",
            "الأوقات بتوقيت الرياض. الموعد المحدد بتاريخ فقط يمتد حتى 23:59 من ذلك اليوم.",
        ],
        "overdue": ["Overdue", "متأخر"],
        "pack": {
            "needsInvestigation": [
                "The final report can be generated once the investigation is approved.",
                "يمكن إنشاء التقرير النهائي بعد اعتماد التحقيق.",
            ],
            "needsInvestigationMaybe": [
                "Needs the approved investigation: the pack is refused until then.",
                "يتطلب اعتماد التحقيق: تُرفض الحزمة قبل ذلك.",
            ],
            "needsIdentity": [
                "This pack holds the injured person's identity. Only users with access to injured-person identity generate it: ask the HSE Officer.",
                "تحتوي هذه الحزمة على هوية المصاب. لا يُنشئها إلا من يملك صلاحية الاطلاع على هوية المصاب: تواصل مع مسؤول السلامة.",
            ],
            "repApprovesGosi": [
                "An HSE Officer approves this pack. Contractor HSE Reps approve GOSI work-injury packs only.",
                "يعتمد مسؤول السلامة هذه الحزمة. ممثل السلامة لدى المقاول يعتمد حزم إصابات العمل للتأمينات فقط.",
            ],
            "endLabel": ["Approve or replace this version", "اعتماد هذه النسخة أو استبدالها"],
        },
    },
}
