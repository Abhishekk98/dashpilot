You are a senior Power BI developer. Suggest up to 6 additional DAX measures that answer the
business goals below and are NOT already in the existing measures.

Rules (measures that break them are rejected automatically):
- Use only tables and columns that exist in the model below; quote table names: 'table'[column].
- Reference existing measures as [Measure Name]; never reference a measure you define in the same answer
  unless it comes earlier in your list.
- Use DIVIDE for every ratio. Use the marked date table only if it is in the model.
- Write plain DAX expressions without the "Name =" prefix, no comments.
- `format` is one of: currency, whole, decimal, percent.
- `folder` is one of: "01 Base Measures", "02 Ratios & Margins", "03 Time Intelligence", "04 Rankings & Pareto", "05 Custom".
- `description` explains the business meaning in one or two plain sentences.

Business goals: {goals}
Industry: {industries}
Audience: {audiences}

Model:
{model}
