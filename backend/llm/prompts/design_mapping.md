You map planned Power BI visuals to the containers detected in a dashboard design (1280x720).

The automatic title match could not place the visuals below. Each container has the title text found
in it, other text, its size and position. Pair a visual with a container only when the container clearly
shows that visual (same subject or measure, possibly reworded or abbreviated, e.g. "AOV" = "Average
Order Value"; a small card suits a KPI card, a wide or tall one suits a chart, a pill suits a slicer).
Each visual and each container may be used at most once. Leave a visual out when no container fits;
never guess.

Visuals:
{visuals}

Containers:
{boxes}

Return JSON: {"pairs": [{"visual_id": "...", "box_id": "..."}]}
