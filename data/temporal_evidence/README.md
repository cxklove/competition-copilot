# Reviewed temporal evidence (presentation only)

`candidates.json` is an explicit, versioned selection of existing official Raw
quotes for Competition Detail. It is not a seed, calendar, live observation, or
source of planning deadlines. No dates were fetched or automatically extracted.

The PX2.4 design review and implementation request authorize the initial
presentation admissions: Huawei edition registration date, RoboMaster edition
registration clock range, and MEICC edition competition month range. Each has a
review note describing its limited scope and why it remains unstructured.
No individual reviewer identity or P12 approval authority is fabricated.

Candidate IDs bind all snapshot content, including the original Raw digest,
quoted text, locator, exact edition, source, precision and review reference.
Admission entries bind those IDs. These repository-managed records are trusted
offline inputs, not a public endpoint for accepting approval or arbitrary quotes.
Changing a selection requires review of the content and its admission binding.

At adapter initialization, the loader checks Raw digest, canonical identities,
allowed field/locator, quoted substring and source metadata against the reviewed
edition provenance. It caches immutable snapshots; detail requests read only the
cache. File edits require host recreation and validation.

Source verification and temporal verification are separate: these sources are
verified, while the temporal interpretation remains `pending`. Rejected and
verified-status candidates are not published as pending evidence. Merely setting
`verified` never creates a TimeWindow.

Huawei finals-week and mathematics competition stage schedules were not admitted
as whole-edition competition windows. Edition evidence is never track-specific.
Date-only/month evidence must not gain inferred clock times, timezones or bounds.

Formal promotion requires explicit Raw structured values and temporal provenance,
new Raw digest binding, P2 human approval, verification and seed validation.
Candidates do not enter P8, P9 Snapshots, CompetitionEvent, Impact or Replanning.
