-- 본 평가가 파트마다 1편씩 녹음하므로 제출당 대화 수를 2~3편으로 넓힌다.
-- returned_submissions는 submissions의 제약을 그대로 복사했으므로 함께 바꾼다.
do $$
declare r record;
begin
  for r in
    select c.conrelid::regclass as tbl, c.conname
    from pg_constraint c
    where c.conrelid in ('public.submissions'::regclass, 'public.returned_submissions'::regclass)
      and c.contype = 'c' and pg_get_constraintdef(c.oid) like '%cardinality%'
  loop
    execute format('alter table %s drop constraint %I', r.tbl, r.conname);
  end loop;
end $$;

alter table public.submissions
  add constraint submissions_dialogue_count check (
    cardinality(dialogue_ids) between 2 and 3
    and cardinality(files) = cardinality(dialogue_ids)
    and cardinality(durations) = cardinality(dialogue_ids));
alter table public.returned_submissions
  add constraint returned_submissions_dialogue_count check (
    cardinality(dialogue_ids) between 2 and 3
    and cardinality(files) = cardinality(dialogue_ids)
    and cardinality(durations) = cardinality(dialogue_ids));
