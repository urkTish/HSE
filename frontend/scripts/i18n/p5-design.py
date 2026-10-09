# Phase 5 design pass (UI/UX): presentation-only strings for the training screens. New keys, plus the
# import commit lines, which read "1 rows can be imported" / "Import 1 rows" (now ICU plurals).
P = {
    "training": {
        "matrix": {
            "fromLabel": ["from", "من"],
        },
        "records": {
            "laterActions": ["Actions on an accepted record", "إجراءات على سجل معتمد"],
        },
        "imports": {
            "partialCommit": [
                "{ok, plural, one {# row can be imported} other {# rows can be imported}}; {err, plural, one {# row with errors will be skipped} other {# rows with errors will be skipped}}.",
                "{ok, plural, one {يمكن استيراد صف واحد} two {يمكن استيراد صفين} few {يمكن استيراد # صفوف} other {يمكن استيراد # صف}}؛ {err, plural, one {وسيتم تجاوز صف واحد به أخطاء} two {وسيتم تجاوز صفين بهما أخطاء} few {وسيتم تجاوز # صفوف بها أخطاء} other {وسيتم تجاوز # صف بها أخطاء}}.",
            ],
            "commit": [
                "{n, plural, one {Import # row} other {Import # rows}}",
                "{n, plural, one {استيراد صف واحد} two {استيراد صفين} few {استيراد # صفوف} other {استيراد # صف}}",
            ],
        },
    },
}
