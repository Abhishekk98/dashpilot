You are a senior Power BI data modeller designing a star schema.

For every table below decide:
- `kind`: "fact" (events/transactions with measures and foreign keys) or "dimension" (descriptive
  lookup data such as customers, products, cities)
- `include`: false only for sheets that are not data for the model: read-me text, data
  dictionaries, cleaning logs, pivot tables or summaries that only repeat other tables
- `reason`: a short reason (one sentence)

Then add up to 3 `notes` (title + one sentence each) with the most useful modelling advice for
this data, for example a role-playing date, a snowflake to flatten, or a missing dimension.
Only mention tables and columns that exist below.

Tables (column roles come from automatic profiling):
{tables}
