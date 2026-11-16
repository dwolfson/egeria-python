# pyegeria (next release, unreleased)

Notes collected for the next release. The version number is set when it's cut. Since 6.3.0, fixes branch from
`main` (the old `release/next` branch is retired). What shipped in 6.3.0 is in the 6.3.0 notes.

## Queued (not yet written)

These are recorded in the issues register; each gets a line here when its fix lands.

- RK-16: Dr.Egeria's Create duplicate check falls back to an untyped lookup and can match a same-named Report.
- PY-21 (second half): `FOR_INFO` in the generated activity-status columns, through the Dr.Egeria command specs.
- PY-22: a find that times out or fails must raise or say "not measured", never return `[]`.
- PY-23: `get_related_elements(..., start_at_end=1)` also returned an end-2 relationship (needs triage).
- PY-24: a get of an element Egeria hides from the caller (OMAG-REPOSITORY-HANDLER-400-010) raises a generic
  exception; it should say "not visible".

## New

## Changed

## Fixes
