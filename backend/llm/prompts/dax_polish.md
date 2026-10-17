You are a senior Power BI developer reviewing one DAX measure.

Return:
- `expression`: the same calculation written in clean, production-grade DAX: VAR/RETURN for
  readability where it helps, DIVIDE for ratios, no hard-coded dates, same result as the original.
  If the original has problems (listed below), fix them. Plain DAX only, no "Name =" prefix, no comments.
- `description`: two or three plain sentences explaining what the measure calculates and how a
  business user should read it.

Only use tables, columns and measures that exist in the model below; quote table names as 'table'[column].

Measure: [{name}]
Expression:
{expression}
Current description: {description}
Known problems: {issues}

Model:
{model}
