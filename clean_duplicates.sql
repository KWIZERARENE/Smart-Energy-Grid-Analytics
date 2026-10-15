DO $$
DECLARE
  c regclass;
  n bigint;
  total bigint := 0;
BEGIN
  FOR c IN
    SELECT format('%I.%I', chunk_schema, chunk_name)::regclass
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'energy_readings'
    ORDER BY range_start
  LOOP
    EXECUTE format(
      'DELETE FROM %s WHERE ctid IN (
         SELECT ctid FROM (
           SELECT ctid, row_number() OVER (PARTITION BY meter_id, event_time ORDER BY received_time) AS rn
           FROM %s) t
         WHERE rn > 1)', c, c);
    GET DIAGNOSTICS n = ROW_COUNT;
    total := total + n;
    RAISE NOTICE 'chunk % : deleted %', c, n;
  END LOOP;
  RAISE NOTICE 'TOTAL DELETED: %', total;
END $$;