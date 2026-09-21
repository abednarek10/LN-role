-- ============================================================================
-- Event-Level Economics
-- ============================================================================
-- What: Full P&L per event for the current tour: gross revenue, variable
--       cost, fixed cost allocation, contribution margin, and contribution
--       margin %.
-- Why : What a strategy manager copy-pastes into a leadership deck.
-- ============================================================================

SELECT
    e.id                                         AS event_id,
    e.artist_name,
    e.tour_name,
    e.event_name,
    v.city,
    v.state,
    e.event_date::date                           AS event_date,
    v.capacity,
    SUM(t.quantity_sold)                         AS tickets_sold,
    SUM(t.quantity_available)                    AS tickets_available,
    ROUND(SUM(t.quantity_sold)::numeric / NULLIF(SUM(t.quantity_available), 0), 4) AS sell_through,
    ROUND(SUM(t.face_value * t.quantity_sold), 2)                    AS gross_revenue,
    ROUND(SUM(t.variable_cost_per_ticket * t.quantity_sold), 2)      AS variable_cost_total,
    ROUND(MAX(t.fixed_cost_per_event), 2)                            AS fixed_cost_allocated,
    ROUND(
        SUM(t.face_value * t.quantity_sold)
        - SUM(t.variable_cost_per_ticket * t.quantity_sold)
        - MAX(t.fixed_cost_per_event),
    2)                                                               AS contribution_margin,
    ROUND(
        (
            SUM(t.face_value * t.quantity_sold)
            - SUM(t.variable_cost_per_ticket * t.quantity_sold)
            - MAX(t.fixed_cost_per_event)
        ) / NULLIF(SUM(t.face_value * t.quantity_sold), 0),
    4)                                                               AS contribution_margin_pct
FROM events e
JOIN venues v  ON v.id = e.venue_id
JOIN tickets t ON t.event_id = e.id
GROUP BY e.id, e.artist_name, e.tour_name, e.event_name, v.city, v.state, e.event_date, v.capacity
ORDER BY e.event_date;
