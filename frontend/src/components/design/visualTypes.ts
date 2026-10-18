/** Power BI native visual types the planner allows, with display labels and icons. */
export const TYPE_LABELS: Record<string, string> = {
  card: "Card",
  slicer: "Slicer",
  text_box: "Text box",
  line: "Line chart",
  area: "Area chart",
  clustered_bar: "Clustered bar",
  clustered_column: "Clustered column",
  stacked_bar: "Stacked bar",
  stacked_column: "Stacked column",
  donut: "Donut",
  map: "Map",
  filled_map: "Filled map",
  table: "Table",
  matrix: "Matrix",
  gauge: "Gauge",
  scatter: "Scatter",
  waterfall: "Waterfall",
  funnel: "Funnel",
};

export const TYPE_ICONS: Record<string, string> = {
  card: "pin",
  slicer: "filter_alt",
  text_box: "lightbulb",
  line: "show_chart",
  area: "area_chart",
  clustered_bar: "align_horizontal_left",
  clustered_column: "bar_chart",
  stacked_bar: "stacked_bar_chart",
  stacked_column: "stacked_bar_chart",
  donut: "donut_large",
  map: "location_on",
  filled_map: "map",
  table: "table_chart",
  matrix: "grid_on",
  gauge: "speed",
  scatter: "scatter_plot",
  waterfall: "waterfall_chart",
  funnel: "filter_list",
};

/** Chart types that show several measures side by side. */
export const MULTI_MEASURE = new Set(["table", "matrix", "clustered_column", "clustered_bar", "line", "scatter"]);
