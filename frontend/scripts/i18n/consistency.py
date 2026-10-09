# Cross-module consistency pass (UI/UX): presentation-only strings that bring the Phase 0–4 and 6a screens up to
# the 6b–6d conventions. New keys live under "consistency"; the other entries replace count strings that read
# "1 days" / "{n} scaffold(s)" with ICU plurals in EN and AR (same placeholders; where the screen shows a
# pre-formatted figure such as `{days}`, the call also passes the plain number `n` that picks the plural form).
# merge.py runs this file after the phase files, so a full merge keeps these values.

# Arabic day counts: 1 يوم واحد, 2 يومان, 3–10 أيام, 11–99 يومًا, 100+ يوم.
_DAYS_OVERDUE = [
    "{n, plural, one {{days} day overdue} other {{days} days overdue}}",
    "{n, plural, one {متأخر يومًا واحدًا} two {متأخر يومين} few {متأخر {days} أيام} many {متأخر {days} يومًا} other {متأخر {days} يوم}}",
]

P = {
    "consistency": {
        "recordActions": ["Record actions", "إجراءات السجل"],
        "siteActions": ["Affects every scaffold in use", "يشمل كل السقالات المستخدمة"],
    },
    # Phase 0–1
    "observations": {
        "photoCount": [
            "{count, plural, one {# photo selected} other {# photos selected}}",
            "{count, plural, one {تم اختيار صورة واحدة} two {تم اختيار صورتين} few {تم اختيار # صور} many {تم اختيار # صورة} other {تم اختيار # صورة}}",
        ],
    },
    "imports": {
        "committed": [
            "{count, plural, one {Import committed: # row saved as submitted.} other {Import committed: # rows saved as submitted.}}",
            "{count, plural, one {تم اعتماد الاستيراد: حُفظ صف واحد كمقدم.} two {تم اعتماد الاستيراد: حُفظ صفان كمقدمين.} few {تم اعتماد الاستيراد: حُفظت # صفوف كمقدمة.} many {تم اعتماد الاستيراد: حُفظ # صفًا كمقدم.} other {تم اعتماد الاستيراد: حُفظ # صف كمقدم.}}",
        ],
    },
    "ca": {"daysOverdue": _DAYS_OVERDUE},
    "dashboard": {
        "daysOverdue": _DAYS_OVERDUE,
        "daysLeft": [
            "{n, plural, one {{days} day left} other {{days} days left}}",
            "{n, plural, one {متبقٍ يوم واحد} two {متبقٍ يومان} few {متبقٍ {days} أيام} many {متبقٍ {days} يومًا} other {متبقٍ {days} يوم}}",
        ],
        "records": [
            "{n, plural, one {{count} record} other {{count} records}}",
            "{n, plural, zero {لا سجلات} one {سجل واحد} two {سجلان} few {{count} سجلات} many {{count} سجلًا} other {{count} سجل}}",
        ],
        "longestRun": [
            "{n, plural, one {Longest run {days} day} other {Longest run {days} days}}",
            "{n, plural, one {أطول فترة يوم واحد} two {أطول فترة يومان} few {أطول فترة {days} أيام} many {أطول فترة {days} يومًا} other {أطول فترة {days} يوم}}",
        ],
    },
    # Phase 2
    "passes": {
        "staleHint": [
            "{days, plural, one {Lodged with the pass office # day ago without a decision.} other {Lodged with the pass office # days ago without a decision.}}",
            "{days, plural, one {قُدِّم لمكتب التصاريح منذ يوم واحد دون قرار.} two {قُدِّم لمكتب التصاريح منذ يومين دون قرار.} few {قُدِّم لمكتب التصاريح منذ # أيام دون قرار.} many {قُدِّم لمكتب التصاريح منذ # يومًا دون قرار.} other {قُدِّم لمكتب التصاريح منذ # يوم دون قرار.}}",
        ],
    },
    # Phase 3
    "permitDetail": {
        "isoPoints": [
            "{n, plural, one {# point} other {# points}} · {locks, plural, one {# personal lock} other {# personal locks}}",
            "{n, plural, zero {لا نقاط} one {نقطة واحدة} two {نقطتان} few {# نقاط} many {# نقطة} other {# نقطة}} · {locks, plural, zero {لا أقفال شخصية} one {قفل شخصي واحد} two {قفلان شخصيان} few {# أقفال شخصية} many {# قفلًا شخصيًا} other {# قفل شخصي}}",
        ],
    },
    # Phase 4
    "scaffolds": {
        "countN": [
            "{n, plural, one {# scaffold} other {# scaffolds}}",
            "{n, plural, zero {لا سقالات} one {سقالة واحدة} two {سقالتان} few {# سقالات} many {# سقالة} other {# سقالة}}",
        ],
        "reinspectionDone": [
            "{n, plural, one {# scaffold now needs re-inspection} other {# scaffolds now need re-inspection}}",
            "{n, plural, zero {لا سقالات تحتاج إعادة فحص} one {سقالة واحدة تحتاج الآن إعادة فحص} two {سقالتان تحتاجان الآن إعادة فحص} few {# سقالات تحتاج الآن إعادة فحص} many {# سقالة تحتاج الآن إعادة فحص} other {# سقالة تحتاج الآن إعادة فحص}}",
        ],
    },
    "equipment": {
        "configRecorded": [
            "{n, plural, one {Configuration event recorded — # certificate line suspended} other {Configuration event recorded — # certificate lines suspended}}",
            "{n, plural, zero {تم تسجيل حدث التهيئة — لم يُعلَّق أي بند شهادة} one {تم تسجيل حدث التهيئة — عُلِّق بند شهادة واحد} two {تم تسجيل حدث التهيئة — عُلِّق بندا شهادة} few {تم تسجيل حدث التهيئة — عُلِّقت # بنود شهادة} many {تم تسجيل حدث التهيئة — عُلِّق # بندًا} other {تم تسجيل حدث التهيئة — عُلِّق # بند شهادة}}",
        ],
    },
    "certImports": {
        "committed": [
            "{n, plural, one {# certificate created} other {# certificates created}}",
            "{n, plural, zero {لم تُنشأ أي شهادة} one {تم إنشاء شهادة واحدة} two {تم إنشاء شهادتين} few {تم إنشاء # شهادات} many {تم إنشاء # شهادة} other {تم إنشاء # شهادة}}",
        ],
    },
    # Phase 6a
    "medical": {
        "settings": {
            "saved": [
                "{n, plural, one {# setting saved.} other {# settings saved.}}",
                "{n, plural, zero {لم يُحفظ أي إعداد.} one {تم حفظ إعداد واحد.} two {تم حفظ إعدادين.} few {تم حفظ # إعدادات.} many {تم حفظ # إعدادًا.} other {تم حفظ # إعداد.}}",
            ],
        },
        "imports": {
            "commit": [
                "{n, plural, one {Commit # row} other {Commit # rows}}",
                "{n, plural, one {اعتماد صف واحد} two {اعتماد صفين} few {اعتماد # صفوف} many {اعتماد # صفًا} other {اعتماد # صف}}",
            ],
            "committed": [
                "{n, plural, one {# record created.} other {# records created.}}",
                "{n, plural, zero {لم يُنشأ أي سجل.} one {تم إنشاء سجل واحد.} two {تم إنشاء سجلين.} few {تم إنشاء # سجلات.} many {تم إنشاء # سجلًا.} other {تم إنشاء # سجل.}}",
            ],
        },
        "gaps": {
            "total": [
                "{n, plural, one {# gap as of {d}} other {# gaps as of {d}}}",
                "{n, plural, zero {لا فجوات حتى {d}} one {فجوة واحدة حتى {d}} two {فجوتان حتى {d}} few {# فجوات حتى {d}} many {# فجوة حتى {d}} other {# فجوة حتى {d}}}",
            ],
        },
    },
}
