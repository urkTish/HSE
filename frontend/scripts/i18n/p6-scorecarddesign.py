# Phase 6g design pass (UI/UX): presentation-only strings for the contractor scorecard and reports screens
# (register, card, comments and disputes, watch list, settings, report packs, exports, performance summary).
# New keys only (scDesign.*); no earlier string is changed.
P = {
    "scDesign": {
        "cappedFrom": ["The score's band was {band}; a cap lowered the grade", "كانت فئة الدرجة {band}؛ وخفّض سقفٌ التقدير"],
        "cappedLine": ["Lowered from band {band} to {grade} by", "خُفّض من الفئة {band} إلى {grade} بسبب"],
        "capNoEffect": ["A cap applies, but the score's band is already at or below it.", "ينطبق سقف، لكن فئة الدرجة عنده أو دونه أصلاً."],
        "capBecause": ["Because of", "بسبب"],
        "aboveMedian": ["Above the project median", "أعلى من وسيط المشروع"],
        "belowMedian": ["Below the project median", "أدنى من وسيط المشروع"],
        "atMedian": ["At the project median", "عند وسيط المشروع"],
        "othersAnonymous": [
            "Other contractors' names and scores are not shown to contractor reps.",
            "لا تظهر أسماء المقاولين الآخرين ودرجاتهم لممثلي المقاولين.",
        ],
        "repScope": [
            "Only your own contractors are listed. Ranks are out of {n} ranked contractors on the project; the others are not named.",
            "تظهر مقاولوك فقط. الترتيب من بين {n} مقاولين مرتبين في المشروع؛ ولا تُذكر أسماء الآخرين.",
        ],
        "window": {
            "open": ["Comment window open", "نافذة التعليقات مفتوحة"],
            "closed": ["Comment window closed: awaiting the HSE Manager's Final", "نافذة التعليقات مغلقة: بانتظار اعتماد مدير السلامة النهائي"],
            "final": ["Final: comments and disputes are closed", "نهائي: أُغلقت التعليقات والاعتراضات"],
            "not_issued": ["Not issued yet: comments open when the card is issued", "لم تُصدر بعد: تُفتح التعليقات عند إصدار البطاقة"],
            "until": ["until {at}", "حتى {at}"],
            "closedAt": ["closed {at}", "أُغلقت {at}"],
        },
        "printing": ["Preparing the PDF…", "جارٍ إعداد ملف PDF…"],
        "performance": ["Performance summary", "ملخص الأداء"],
        "pack": {
            "notIssuedShort": ["Not issued", "لم تُصدر"],
            "draftTitle": ["Draft: not issued", "مسودة: لم تُصدر"],
            "draftBody": [
                "Nobody on the distribution list has received it. Rebuilding refreshes the figures from current data.",
                "لم يستلمها أحد من قائمة التوزيع. إعادة البناء تحدّث الأرقام من البيانات الحالية.",
            ],
            "reviewTitle": ["In review: not issued", "قيد المراجعة: لم تُصدر"],
            "reviewBody": [
                "Nobody on the distribution list has received it. Issue needs a review by someone other than the issuer.",
                "لم يستلمها أحد من قائمة التوزيع. يتطلب الإصدار مراجعة من شخص غير المُصدِر.",
            ],
            "issuedTitle": ["Issued {at} by {by}", "صدرت {at} بواسطة {by}"],
            "issuedTitleShort": ["Issued", "صدرت"],
            "provisionalTitle": ["Provisional scorecards", "بطاقات أداء مؤقتة"],
            "provisionalBody": [
                "The month's scorecards were not Final at issue. The scorecard section carries the PROVISIONAL watermark and can still change through contractor comment.",
                "لم تكن بطاقات أداء الشهر نهائية عند الإصدار. يحمل قسم بطاقات الأداء علامة «مؤقت» وقد يتغير بتعليقات المقاولين.",
            ],
            "endIssue": ["Issue: freezes the files and notifies the list", "الإصدار: يجمّد الملفات ويُبلغ القائمة"],
            "endReissue": ["Replace this issued pack with a new revision", "استبدال هذه الحزمة الصادرة بمراجعة جديدة"],
        },
        "watch": {
            "endLabel": ["Decide or close this entry", "القرار أو إغلاق هذا القيد"],
            "ladder": ["Watch-list level", "مستوى قائمة المراقبة"],
            "here": ["Current level", "المستوى الحالي"],
            "wasHere": ["Level when closed", "المستوى عند الإغلاق"],
        },
        "profile": {
            "sumOff": ["should total 100", "يجب أن يكون المجموع 100"],
            "saveFirst": ["Save the changes before activating.", "احفظ التغييرات قبل التفعيل."],
        },
    },
}
