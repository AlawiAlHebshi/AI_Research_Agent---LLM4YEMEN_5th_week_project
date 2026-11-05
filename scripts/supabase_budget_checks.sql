-- Append to an installation with every ai_budget_ prefix renamed ai_budget_check_.
-- Replace its COMMIT with this block and ROLLBACK; production rows are untouched.
do $$
declare r jsonb; sid text; i integer; caught boolean := false;
begin
    if has_function_privilege('anon','public.ai_budget_check_snapshot(text)','execute')
       or has_function_privilege('authenticated','public.ai_budget_check_reserve(text,text,integer,integer)','execute')
       or has_schema_privilege('service_role','ai_budget_check_private','usage') then
        raise exception 'FAIL: unauthorized role grants';
    end if;
    r := public.ai_budget_check_snapshot(null);
    if r->>'code' <> 'ledger_uninitialized' then raise exception 'FAIL: initialization guard'; end if;
    perform ai_budget_check_private.seed(200, (now() at time zone 'Asia/Aden')::date,100,50,4);
    r := public.ai_budget_check_snapshot(null);
    if (r->>'project_nanos')::bigint <> 200 or (r->>'day_nanos')::bigint <> 100
       or (r->>'reserved_nanos')::bigint <> 50 or (r->>'calls')::integer <> 4 then
        raise exception 'FAIL: baseline preservation';
    end if;
    begin
        perform ai_budget_check_private.seed(0,current_date,0,0,0);
    exception when others then caught := true;
    end;
    if not caught then raise exception 'FAIL: reseed allowed'; end if;
    for i in 1..10 loop
        sid := lpad(i::text,32,'0');
        r := public.ai_budget_check_reserve('turns',sid,10,10);
        if not (r->>'ok')::boolean then raise exception 'FAIL: valid reservation'; end if;
    end loop;
    r := public.ai_budget_check_reserve('turns',repeat('a',32),10,10);
    if r->>'code' <> 'turn_limit' then raise exception 'FAIL: turn cap'; end if;
    r := public.ai_budget_check_reserve('duplicate',lpad('1',32,'0'),10,10);
    if r->>'code' <> 'invalid_reservation' then raise exception 'FAIL: duplicate request'; end if;
    r := public.ai_budget_check_settle(lpad('1',32,'0'),3,1,4);
    if r->>'code' <> 'invalid_usage' then raise exception 'FAIL: invalid cached usage'; end if;
    r := public.ai_budget_check_settle(lpad('1',32,'0'),3,1,0);
    if not (r->>'ok')::boolean then raise exception 'FAIL: valid settlement'; end if;
    r := public.ai_budget_check_settle(lpad('1',32,'0'),3,1,0);
    if not (r->>'ok')::boolean then raise exception 'FAIL: idempotent settlement'; end if;
    r := public.ai_budget_check_settle(lpad('1',32,'0'),0,0,0);
    if r->>'code' <> 'invalid_usage' then raise exception 'FAIL: settlement reduction'; end if;
    r := public.ai_budget_check_settle(lpad('2',32,'0'),20,1,0);
    if not (r->>'exceeded')::boolean then raise exception 'FAIL: exceeded bound'; end if;
    r := public.ai_budget_check_reserve('taskcap',repeat('b',32),200000,1200);
    if not (r->>'ok')::boolean then raise exception 'FAIL: task first call'; end if;
    r := public.ai_budget_check_reserve('taskcap',repeat('c',32),200000,1200);
    if r->>'code' <> 'task_budget' then raise exception 'FAIL: task cap'; end if;
    -- Manipulate ONLY the temporary check account, never the real ledger.
    update ai_budget_check_private.account set baseline_project=5000000000-1,
        baseline_daily=0, baseline_reserved=0 where id=1;
    r := public.ai_budget_check_reserve('projectcap',repeat('d',32),10,10);
    if r->>'code' <> 'project_budget' then raise exception 'FAIL: project cap'; end if;
    update ai_budget_check_private.account set baseline_project=300000000,
        baseline_daily=300000000, baseline_reserved=0 where id=1;
    r := public.ai_budget_check_reserve('daycap',repeat('e',32),10,10);
    if r->>'code' <> 'daily_budget' then raise exception 'FAIL: daily cap'; end if;
end; $$;
rollback;
select 'PASS: isolated SQL budget checks; all test objects rolled back' as result;
