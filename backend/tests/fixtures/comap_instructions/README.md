# COMAP parser fixtures

`schedule.html` is a minimal **synthetic test fixture**, not a captured website
response or official historical update. Its title/strong-heading/ul/li structure
matches the official instructions page inspected during P9.5.3 development.
Its three date facts match the existing reviewed COMAP MCM 2027 Seed.

Reviewed source: https://contest.comap.com/undergraduate/contests/mcm/instructions.php

Tests derive missing/date-only/invalid structures from this fixture in memory.
Those variants are synthetic adapter responses, not claims about official changes.
They lock bounded parsing, source-explicit EST = UTC-05:00 (already reviewed),
failure versus successful UNKNOWN, and the exclusion of problem labels from tracks.
No default test accesses the network or mutates official data.
