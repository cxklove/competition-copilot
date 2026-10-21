# P6 verified skill route: review packet

Human decision on 2026-10-20: **APPROVE both facts and the new Skill ID**, explicitly
supplied by the user after reviewing this packet. The two approved artifacts are
now in `data/skill_requirements/c4-big-data-challenge-2026.json` and
`data/skill_requirements/china-graduate-math-modeling-2026.json`; no draft JSON
remains in this review directory. Source observation did not substitute for this
separate semantic approval. No scores or weights were approved or implemented.

## Approved interpretations

1. C4 / c4-big-data-challenge-2026, edition-level: add one REQUIRED
   `machine-learning-modeling` presence fact. Official 2026 introduction explicitly
   describes constructing machine-learning models from historical data to predict
   future returns. Source: https://nercbds.tsinghua.edu.cn/bdc.html (2026 edition
   introduction and task description, independently observed 2026-10-20).
2. China Graduate Mathematical Modeling / china-graduate-math-modeling-2026,
   edition-level: reuse the exact existing `mathematical-modeling` Skill definition
   and add one REQUIRED presence fact. The 2026 invitation explicitly describes
   building mathematical models to solve practical problems; this is not inferred
   from the competition title. Source:
   https://cpipc.acge.org.cn/cw/contestNews/detail/4/2c9080189dcfa24e019dddacc24a1314
   (opening paragraph, independently observed 2026-10-20).

For both, REQUIRED means a structured interpretation of core task capability,
not an official categorical label or P5 participation restriction.
`required_level=null`, level evidence empty, and coverage PARTIAL. Neither source
defines BEGINNER/INTERMEDIATE/ADVANCED or establishes complete skill coverage.

## Taxonomy decision

Only one new ID is added: `machine-learning-modeling`, defined as constructing
and evaluating machine-learning models from data, without assuming a programming
language or framework. It is a data-driven model-development capability, distinct
from the existing general mathematical-modeling identity. No Python aliases,
synonym IDs, brand preference or invented popularity signal are added.

## Curated set and fixture

The four-candidate set is gcxl 2027, COMAP MCM 2027, C4 2026 and China Graduate
Mathematical Modeling 2026. GCXL remains requirement-unavailable: reviewed
track names and participation constraints do not establish universal edition-level
skill requirements. COMAP retains its existing human-approved one-skill artifact.

`data/local_runtime/recommendation_demo.json` is a clearly synthetic, fixed
applied-mathematics student with mathematical-modeling proficiency. It is not
generated from candidate lists, requirement scores or an LLM. Requirement-ID
overlap is a data check only; absence is not zero ability or a suitability score.

Approval covers promotion of these two exact facts and the single new Skill
definition to the formal requirement directory. It does not approve a scoring
policy, proficiency threshold, P5 change or P6 score.
