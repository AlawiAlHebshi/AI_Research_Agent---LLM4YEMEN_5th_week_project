-- Run once in the dedicated FREE project's SQL Editor. No credentials here.
-- Schema installation never initializes or resets the financial ledger.
begin;
create schema if not exists ai_budget_private;
revoke all on schema ai_budget_private from public, anon, authenticated, service_role;

create table if not exists ai_budget_private.account (
    id integer primary key check (id = 1),
    seeded boolean not null default false,
    baseline_project bigint not null default 0 check (baseline_project >= 0),
    baseline_day date,
    baseline_daily bigint not null default 0 check (baseline_daily >= 0),
    baseline_reserved bigint not null default 0 check (baseline_reserved >= 0),
    baseline_calls bigint not null default 0 check (baseline_calls >= 0),
    check (baseline_daily <= baseline_project and baseline_reserved <= baseline_project)
);
insert into ai_budget_private.account (id) values (1) on conflict do nothing;
create table if not exists ai_budget_private.calls (
    id text primary key check (id ~ '^[a-f0-9]{32}$'),
    task text not null check (task ~ '^[a-zA-Z0-9_-]{1,100}$'),
    day date not null,
    status text not null check (status in ('reserved', 'measured')),
    charge bigint not null check (charge >= 0),
    input_bound integer not null check (input_bound between 1 and 200000),
    output_bound integer not null check (output_bound between 1 and 1200),
    input_tokens integer, output_tokens integer, cached_tokens integer,
    created_at timestamptz not null default now()
);
create index if not exists ai_budget_task_idx on ai_budget_private.calls(task);
alter table ai_budget_private.account enable row level security;
alter table ai_budget_private.calls enable row level security;
revoke all on all tables in schema ai_budget_private from public, anon, authenticated, service_role;

-- Admin-only one-time seed. Never exposed as a Data API operation.
create or replace function ai_budget_private.seed(p_project bigint, p_day date,
    p_daily bigint, p_reserved bigint, p_calls bigint) returns void
language plpgsql security definer set search_path = '' as $$
declare a ai_budget_private.account%rowtype;
begin
    select * into strict a from ai_budget_private.account where id = 1 for update;
    if a.seeded then raise exception 'Ledger already initialized; no reset is permitted'; end if;
    if p_project is null or p_day is null or p_daily is null or p_reserved is null or p_calls is null
       or least(p_project, p_daily, p_reserved, p_calls) < 0
       or p_daily > p_project or p_reserved > p_project then
        raise exception 'Invalid baseline';
    end if;
    update ai_budget_private.account set seeded = true, baseline_project = p_project,
        baseline_day = p_day, baseline_daily = p_daily, baseline_reserved = p_reserved,
        baseline_calls = p_calls where id = 1;
end; $$;
revoke all on function ai_budget_private.seed(bigint,date,bigint,bigint,bigint)
    from public, anon, authenticated, service_role;

create or replace function public.ai_budget_snapshot(p_task text default null) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare a ai_budget_private.account%rowtype; d date := (now() at time zone 'Asia/Aden')::date;
begin
    select * into a from ai_budget_private.account where id = 1 for share;
    if not found or not a.seeded then return jsonb_build_object('ok',false,'code','ledger_uninitialized'); end if;
    return (select jsonb_build_object('ok',true,'version',1,'model','gpt-6-luna',
        'task_cap',30000000,'day_cap',300000000,'project_cap',5000000000,
        'max_turns',10,'max_input',200000,'max_output',1200,
        'calls',a.baseline_calls + count(*),
        'task_nanos',coalesce(sum(charge) filter (where task = p_task),0),
        'day_nanos',case when a.baseline_day = d then a.baseline_daily else 0 end +
            coalesce(sum(charge) filter (where day = d),0),
        'project_nanos',a.baseline_project + coalesce(sum(charge),0),
        'reserved_nanos',a.baseline_reserved + coalesce(sum(charge) filter (where status = 'reserved'),0))
        from ai_budget_private.calls);
end; $$;

create or replace function public.ai_budget_reserve(p_task text, p_id text, p_input integer, p_output integer)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare a ai_budget_private.account%rowtype; s jsonb; n bigint;
    d date := (now() at time zone 'Asia/Aden')::date;
begin
    -- One database row serializes ALL reservations and settlements across processes.
    select * into a from ai_budget_private.account where id = 1 for update;
    if not found or not a.seeded then return jsonb_build_object('ok',false,'code','ledger_uninitialized'); end if;
    if p_task is null or p_id is null or p_input is null or p_output is null
       or p_task !~ '^[a-zA-Z0-9_-]{1,100}$' or p_id !~ '^[a-f0-9]{32}$'
       or p_input not between 1 and 200000 or p_output not between 1 and 1200 then
        return jsonb_build_object('ok',false,'code','invalid_bounds');
    end if;
    -- A duplicate is never permission to replay a possibly paid model request.
    if exists(select 1 from ai_budget_private.calls where id = p_id) then
        return jsonb_build_object('ok',false,'code','invalid_reservation');
    end if;
    if (select count(*) from ai_budget_private.calls where task = p_task) >= 10 then
        return jsonb_build_object('ok',false,'code','turn_limit');
    end if;
    n := p_input::bigint * 125 + p_output::bigint * 500;
    s := public.ai_budget_snapshot(p_task);
    if (s->>'task_nanos')::bigint + n > 30000000 then return jsonb_build_object('ok',false,'code','task_budget'); end if;
    if (s->>'day_nanos')::bigint + n > 300000000 then return jsonb_build_object('ok',false,'code','daily_budget'); end if;
    if (s->>'project_nanos')::bigint + n > 5000000000 then return jsonb_build_object('ok',false,'code','project_budget'); end if;
    insert into ai_budget_private.calls(id,task,day,status,charge,input_bound,output_bound)
        values(p_id,p_task,d,'reserved',n,p_input,p_output);
    return jsonb_build_object('ok',true,'reservation',p_id,'estimate',n);
end; $$;

create or replace function public.ai_budget_settle(p_id text, p_input integer, p_output integer, p_cached integer)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare a ai_budget_private.account%rowtype; c ai_budget_private.calls%rowtype; n bigint;
begin
    select * into a from ai_budget_private.account where id = 1 for update;
    if not found or not a.seeded then return jsonb_build_object('ok',false,'code','ledger_uninitialized'); end if;
    if p_input is null or p_output is null or p_cached is null or p_id is null
       or p_input not between 0 and 2000000 or p_output not between 0 and 2000000
       or p_cached not between 0 and p_input then
        return jsonb_build_object('ok',false,'code','invalid_usage');
    end if;
    select * into c from ai_budget_private.calls where id = p_id;
    if not found then return jsonb_build_object('ok',false,'code','invalid_reservation'); end if;
    -- Repeated settlement must match exactly; it cannot lower an earlier charge.
    if c.status = 'measured' then
        if c.input_tokens <> p_input or c.output_tokens <> p_output or c.cached_tokens <> p_cached then
            return jsonb_build_object('ok',false,'code','invalid_usage');
        end if;
    else
        n := (p_input::bigint - p_cached) * 100 + p_cached::bigint * 10 + p_output::bigint * 500;
        update ai_budget_private.calls set status='measured',charge=n,input_tokens=p_input,
            output_tokens=p_output,cached_tokens=p_cached where id=p_id;
    end if;
    return jsonb_build_object('ok',true,'exceeded',p_input > c.input_bound or p_output > c.output_bound);
end; $$;

revoke all on function public.ai_budget_snapshot(text) from public, anon, authenticated;
revoke all on function public.ai_budget_reserve(text,text,integer,integer) from public, anon, authenticated;
revoke all on function public.ai_budget_settle(text,integer,integer,integer) from public, anon, authenticated;
grant execute on function public.ai_budget_snapshot(text) to service_role;
grant execute on function public.ai_budget_reserve(text,text,integer,integer) to service_role;
grant execute on function public.ai_budget_settle(text,integer,integer,integer) to service_role;
notify pgrst, 'reload schema';
commit;
