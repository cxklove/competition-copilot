# Reviewed skill requirement artifacts

P7.3 storage is independent of P2 Seeds/Raw/Manifest and P5 eligibility policies.
`comap-mcm-2027.json` is the first human-reviewed real artifact (P7.3B.4 APPROVE,
authored in P7.3B.5). Its exact Edition target is comap-mcm / comap-mcm-2027 /
track null. It contains only mathematical-modeling, required_level null and
PARTIAL coverage. REQUIRED is a human-reviewed structured interpretation of core
task capability, not an official COMAP enum or P5 hard eligibility constraint.
The official 2027 MCM rules were re-observed for presence evidence; no proficiency
evidence is asserted. The embedded Skill definition is the approved reusable identity.

The checked-in reviewed Seeds support identity, editions, tracks and some dates;
the current eligibility policies support education restrictions. None establishes
exact skill identity, REQUIRED/DESIRED meaning and a grounded proficiency level.
Track titles, competition names and source URLs alone cannot supply these facts.
No Raw/Manifest parsing, web collection or guessed requirements were used.

Edition artifact filenames use the exact edition ID (`comap-mcm-2027.json`).
`*.json` files use `SkillRequirementSetEnvelope`: schema_version `1.0`,
artifact_type `skill_requirement_set`, requirement_version, system review_note,
requirement_set (the unchanged P7.1 model), and a minimal `skills` catalog reusing
Skill fields. Every requirement ID must resolve to the catalog. Shared IDs across
artifacts must have consistent Skill snapshots; this is not a Skill Repository.

Each requirement needs reviewed official source evidence for its skill membership
and type interpretation. `presence_evidence` asserts the canonical fact
`requirements.<skill_id>.present = true`. `required_level` must explicitly be a
known SkillLevel or null (known requirement, unspecified threshold). For a known
threshold, `evidence` must prove `requirements.<skill_id>.required_level` with the
canonical serialized level; for null, that channel must be empty. No fake level
proof or automatic default is allowed. Evidence.message records the
supporting source text/interpretation; review must establish that it actually
supports the declared fact. JSON validation does not perform semantic source review.
Do not default an unspecified proficiency to INTERMEDIATE or ADVANCED.

Coverage is explicitly assessed: PARTIAL unless completeness can be supported.
Requirement-set completeness is independent of threshold completeness; COMPLETE
does not imply every official proficiency threshold was specified.
coverage_note and review_note are system assessments without official-source
attribution. Empty requirements are MISSING only. No artifact lookup returns None,
which a future caller may map to MISSING after validating the target in Repository.
Queries never inherit edition data into tracks or fall back to another year.

The JSON Provider reads files in filename order, loads atomically, rejects invalid
data/duplicate targets/conflicting identities, and never writes artifacts or
accesses Repository, Raw, Manifest, Seed, students, SkillGapEngine, LLM or network.
Real provenance/target smoke now executes against the reviewed artifact. Other
targets remain unavailable unless independently reviewed; None remains missing
data. P7.3 is not declared COMPLETE; P7.4 is not implemented.
