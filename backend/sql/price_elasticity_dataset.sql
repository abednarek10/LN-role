-- ============================================================================
-- Price Elasticity Dataset
-- ============================================================================
-- What: Emit the (price, tickets_sold) panel per event that the log-log
--       elasticity model fits. Useful for exporting to a notebook or
--       benchmarking against a warehouse-side model.
-- Why : Anyone comfortable in a warehouse but not in the Python service
--       should be able to reproduce the same numbers.
-- ============================================================================

SELECT
    hp.event_id,
    e.event_name,
    v.city,
    hp.observation_date,
    hp.avg_price,
    hp.tickets_sold,
    hp.promo_flag,
    LN(hp.avg_price)      AS log_price,
    LN(NULLIF(hp.tickets_sold, 0))   AS log_qty
FROM historical_pricing hp
JOIN events e ON e.id = hp.event_id
JOIN venues v ON v.id = e.venue_id
WHERE hp.avg_price > 0 AND hp.tickets_sold > 0
ORDER BY hp.event_id, hp.observation_date;
