# DS1 archive decision — 2026-10-22

User approved moving BSR and GVR out of the primary DS1 list into the archive.
Primary setup scans now use 18 symbols from `scripts/ds1_universe.py`.
This applies to both live scanner and Pre-Breakout/Paper Watch; archived symbols
cannot be Paper Watch candidates. This membership change is not a BUY signal.

BSR retains original added date 2026-09-22; GVR retains 2026-10-08.
Both remain in the 20-entry performance collector, with original entry-date
logic, raw observations, T+ and adjustment-verification requirements unchanged.
No archived position is rebased to the archive date.

The decision was made after the 22 October close. Performance cohort membership
changes from the next trading session, 2026-10-23. Existing dated 22 October and
earlier bundles remain immutable. New reports retain legacy 20-entry fields,
label their scope, and add ACTIVE (18) and ARCHIVED (2) reference summaries plus
row membership in JSON/CSV/Markdown. Never label the 20-entry mean as the current
18-entry list's return. Reference returns remain unverified until evidence passes.

DS2 holdings, quantities, costs, strategy thresholds and priority are unchanged.
No transaction or Telegram message is triggered by archiving.

Validation: `python -m unittest -v test_ds1_universe test_ds1_paper_watch
test_ds1_performance test_ds1_snapshot test_ds2_eod`.
