Map the user's business question to a query over the Power BI model below. Return JSON only.

- `measure`: exactly one name from `measures`.
- `dimension_table` / `dimension_column`: a pair from `dimensions` if the question asks "by", "which",
  "top" or compares groups; otherwise null.
- `filter_table` / `filter_column` / `filter_value`: only if the question restricts to one value
  (e.g. "in Delhi"); use a pair from `filterable_columns` and the value as written; otherwise null.
- `period`: one of `periods` ("all" when no time period is mentioned).
- `top_n`: how many groups to list (default 5).

Use only names that appear in the schema. Do not write code.

Question: {question}

Schema:
{schema}
