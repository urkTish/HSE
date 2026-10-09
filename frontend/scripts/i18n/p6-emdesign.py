# Phase 6c design pass (UI/UX): presentation-only strings for the emergency screens. New keys, plus the
# drill evaluation "criteria failed" note, which read "1 criteria failed" (now an ICU plural).
_BI = {
    "musterSheet": "Muster sheet|كشف التجمع",
    "musterNo": "Muster|الحصر",
    "musterSite": "Site|الموقع",
    "musterGenerated": "Printed|تاريخ الطباعة",
    "musterWorkerNo": "Worker no.|رقم العامل",
    "musterName": "Name|الاسم",
    "musterPresent": "Present|حاضر",
    "musterNotes": "Notes|ملاحظات",
    "musterOnList": "On this list|في هذه القائمة",
    "musterCountedBy": "Counted by|تم الحصر بواسطة",
    "musterSignature": "Signature|التوقيع",
    "musterTime": "Time|الوقت",
    "musterApWarden": "Assembly point / warden|نقطة التجمع / المراقب",
    "musterConfidential": "Contains names: keep with the muster, destroy after the all clear. Each print is logged.|يحتوي على أسماء: يُحفظ مع الحصر ويُتلف بعد زوال الخطر. تُسجَّل كل طباعة.",
}
P = {
    "accessPrint": {k: [v, v] for k, v in _BI.items()},
    "emDesign": {
        "missingNone": ["No one missing", "لا يوجد مفقودون"],
        "missingSome": ["{n, plural, one {# person missing} other {# people missing}}", "{n, plural, zero {لا مفقودين} one {شخص واحد مفقود} two {شخصان مفقودان} few {# أشخاص مفقودون} many {# شخصًا مفقودًا} other {# شخص مفقود}}"],
        "missingLineSome": ["Search for them or resolve each with a reason.", "ابحث عنهم أو سوِّ وضع كل منهم مع ذكر السبب."],
        "missingLineNone": ["Everyone expected is accounted for or resolved.", "تم حصر جميع المتوقعين أو تسوية أوضاعهم."],
        "progress": ["{done} of {expected} accounted for", "تم حصر {done} من {expected}"],
        "progressNoExpected": ["No one expected on this muster", "لا يوجد متوقعون في هذا الحصر"],
        "dangerZone": ["Record actions", "إجراءات السجل"],
    },
    "emergency": {
        "eval": {
            "failNote": [
                "{n, plural, one {# criterion failed: a finding is added for it.} other {# criteria failed: findings are added for them.}}",
                "{n, plural, one {فشل معيار واحد: تُضاف له ملاحظة.} two {فشل معياران: تُضاف لهما ملاحظات.} other {فشل # من المعايير: تُضاف لها ملاحظات.}}",
            ],
        },
    },
}
