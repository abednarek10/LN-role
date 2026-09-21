-- ============================================================================
-- Market Prioritization Query
-- ============================================================================
-- What: Rank cities on the current tour by a lightweight "opportunity" score
--       that blends sell-through, demand momentum, and revenue density.
-- Why : Strategy owner needs a single sortable list to answer "which markets
--       deserve an extra date / more marketing?" in <30 seconds.
-- Notes: This mirrors backend/services/metrics.opportunity_score in SQL so a
--        BI tool (Tableau / Power BI) can drive the same view off the same
--        numbers without calling the API.
-- ============================================================================

WITH ticket_rollup AS (
    SELECT
        e.id                                        AS event_id,
        v.city                                      AS city,
        v.state                                     AS state,
        v.capacity                                  AS capacity,
        SUM(t.face_value * t.quantity_sold)         AS gross_revenue,
        SUM(t.variable_cost_per_ticket * t.quantity_sold) AS variable_cost,
        MAX(t.fixed_cost_per_event)                 AS fixed_cost,
        SUM(t.quantity_sold)                        AS tickets_sold,
        SUM(t.quantity_available)                   AS tickets_available
    FROM events e
    JOIN venues v      ON v.id = e.venue_id
    JOIN tickets t     ON t.event_id = e.id
    GROUP BY e.id, v.city, v.state, v.capacity
),
demand_rollup AS (
    -- Recent 7-day pageview mean vs the trailing 30-day mean → momentum.
    SELECT
        ds.event_id,
        AVG(CASE WHEN ds.date >= (SELECT MAX(date) FROM demand_signals) - INTERVAL '7 days'
                 THEN ds.page_views END)                             AS recent_pv_mean,
        AVG(CASE WHEN ds.date >= (SELECT MAX(date) FROM demand_signals) - INTERVAL '30 days'
                 THEN ds.page_views END)                             AS baseline_pv_mean
    FROM demand_signals ds
    GROUP BY ds.event_id
)
SELECT
    tr.city,
    tr.state,
    COUNT(*)                                                        AS event_count,
    ROUND(SUM(tr.gross_revenue), 2)                                 AS gross_revenue_usd,
    ROUND(SUM(tr.gross_revenue - tr.variable_cost - tr.fixed_cost), 2) AS contribution_margin_usd,
    ROUND(AVG(tr.tickets_sold::numeric / NULLIF(tr.tickets_available, 0)), 4) AS avg_sell_through,
    ROUND(AVG(COALESCE(dr.recent_pv_mean / NULLIF(dr.baseline_pv_mean, 0), 1.0)), 3)
                                                                    AS avg_demand_momentum,
    -- Same weighted-heuristic form as opportunity_score() in services/metrics.py.
    ROUND(
        100 * (
            0.40 * LEAST(1.0, AVG(tr.tickets_sold::numeric / NULLIF(tr.tickets_available, 0)))
          + 0.35 * LEAST(1.0, GREATEST(0.0,
                (AVG(COALESCE(dr.recent_pv_mean / NULLIF(dr.baseline_pv_mean, 0), 1.0)) - 0.5) / 1.0))
          + 0.25 * 0.5  -- price-gap component defaults to neutral in pure-SQL
        ),
        1
    )                                                                AS opportunity_score
FROM ticket_rollup tr
LEFT JOIN demand_rollup dr USING (event_id)
GROUP BY tr.city, tr.state
ORDER BY opportunity_score DESC, gross_revenue_usd DESC;
