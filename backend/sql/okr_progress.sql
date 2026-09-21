-- ============================================================================
-- OKR Progress — Concerts, North America, 2026
-- ============================================================================
-- What: Roll each event's revenue and contribution margin up to its OKR
--       segment (`<Category>s_<Region>_<Year>`), join against okr_targets,
--       and compute progress %.
-- Why : One-glance answer to "how close are we to the annual target?" —
--       the OKR view in the workbench UI runs this shape.
-- ============================================================================

WITH per_event AS (
    SELECT
        e.id                                          AS event_id,
        CONCAT(
            e.category, 's_',
            CASE WHEN v.country IN ('USA', 'Canada') THEN 'NA' ELSE v.country END,
            '_',
            EXTRACT(YEAR FROM e.event_date)::text
        )                                             AS segment,
        SUM(t.face_value * t.quantity_sold)           AS revenue,
        SUM(t.face_value * t.quantity_sold)
          - SUM(t.variable_cost_per_ticket * t.quantity_sold)
          - MAX(t.fixed_cost_per_event)               AS contribution_margin
    FROM events e
    JOIN venues v  ON v.id = e.venue_id
    JOIN tickets t ON t.event_id = e.id
    GROUP BY e.id, e.category, v.country, e.event_date
),
by_segment AS (
    SELECT
        segment,
        COUNT(*)                          AS events_counted,
        SUM(revenue)                      AS revenue_to_date,
        SUM(contribution_margin)          AS margin_to_date
    FROM per_event
    GROUP BY segment
)
SELECT
    o.segment,
    o.annual_revenue_target,
    o.annual_margin_target,
    COALESCE(bs.events_counted, 0)                    AS events_counted,
    ROUND(COALESCE(bs.revenue_to_date, 0), 2)         AS revenue_to_date,
    ROUND(COALESCE(bs.margin_to_date, 0), 2)          AS margin_to_date,
    ROUND(
        COALESCE(bs.revenue_to_date, 0) / NULLIF(o.annual_revenue_target, 0),
    4)                                                AS revenue_progress_pct,
    ROUND(
        COALESCE(bs.margin_to_date, 0) / NULLIF(o.annual_margin_target, 0),
    4)                                                AS margin_progress_pct
FROM okr_targets o
LEFT JOIN by_segment bs USING (segment)
ORDER BY o.segment;
