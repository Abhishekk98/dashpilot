You are a senior Power BI data modeller reviewing an automatic data profile.

For every column below, decide its semantic role in a Power BI star schema:
- primary_key: uniquely identifies rows of its own table
- foreign_key: points to another table's primary key (set `target_table`)
- identifier: an ID that is neither a key of this table nor clearly linked to another table
- measure: numeric value that should be aggregated (revenue, quantity, price, rate)
- time_dimension: date or timestamp used for time analysis
- geo_dimension: city, state, country, postal code or coordinates
- categorical_slicer: low-cardinality category users will filter by
- flag: yes/no or true/false indicator
- attribute: descriptive text (names, emails, notes)

Each column comes with a rule-based guess. Keep it unless the column name, samples or
statistics clearly show a better role. Numeric codes (zip codes, years used as labels,
phone numbers) are not measures. Give a confidence between 0 and 1.
Return exactly one entry per column, using the table and column names as given.

Profile:
{profile}
