# Checkpoint B — rebuild, validation, inter-annotator comparison

## 17:105

- Source sha256 matches pinned manifest: **True**
- grok: 3 units · verbatim rebuild OK: **True** · validation errors: 0 [] · low-confidence units: 0
- codex: 3 units · verbatim rebuild OK: **True** · validation errors: 0 [] · low-confidence units: 0
- Boundary agreement F1: **1.0** (grok 2, codex 2, shared 2)
- Span-level exact agreement — source tags: **1.0**, content tags: **1.0**, both: **1.0**
- Specialist queue: **0/6 spans**; auto-accept candidates: 6

## 2:255

- Source sha256 matches pinned manifest: **True**
- grok: 13 units · verbatim rebuild OK: **True** · validation errors: 0 [] · low-confidence units: 3
- codex: 13 units · verbatim rebuild OK: **True** · validation errors: 0 [] · low-confidence units: 2
- Boundary agreement F1: **1.0** (grok 12, codex 12, shared 12)
- Span-level exact agreement — source tags: **0.906**, content tags: **0.651**, both: **0.575**
- Specialist queue: **45/106 spans**; auto-accept candidates: 61

## 2:102

- Source sha256 matches pinned manifest: **True**
- grok: 7 units · verbatim rebuild OK: **True** · validation errors: 0 [] · low-confidence units: 2
- codex: 7 units · verbatim rebuild OK: **True** · validation errors: 0 [] · low-confidence units: 3
- Boundary agreement F1: **0.667** (grok 6, codex 6, shared 4)
- Span-level exact agreement — source tags: **0.903**, content tags: **0.774**, both: **0.774**
- Specialist queue: **30/31 spans**; auto-accept candidates: 1

## Totals

```
{
 "spans": 143,
 "span_source_exact": 0.909,
 "span_content_exact": 0.692,
 "span_both_exact": 0.636,
 "specialist_queue_spans": 75
}
```