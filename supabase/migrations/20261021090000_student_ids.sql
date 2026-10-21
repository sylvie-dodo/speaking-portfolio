-- 대학 수업용 학번·학년. 학생은 학번과 이름으로 입장하고, 내부 식별은 기존 (class, number)를 유지한다.
alter table public.students add column student_id text unique, add column grade smallint;

-- 학번과 이름이 모두 맞을 때만 (class, number)를 돌려준다. 하나라도 틀리면 null.
create function private.resolve_student(p_student_id text, p_name text)
returns jsonb language sql security definer set search_path = '' stable as $$
  select jsonb_build_object('class', s.class, 'number', s.number)
  from public.students s
  where upper(btrim(s.student_id)) = upper(btrim(p_student_id))
    and public.norm_name(s.name) = public.norm_name(p_name)
    and public.norm_name(p_name) <> ''
$$;

create function public.resolve_student(p_student_id text, p_name text)
returns jsonb language sql security invoker set search_path = '' stable as $$
  select private.resolve_student(p_student_id, p_name)
$$;

revoke all on function private.resolve_student(text, text), public.resolve_student(text, text) from public, authenticated;
grant execute on function private.resolve_student(text, text), public.resolve_student(text, text) to anon;

create or replace function private.teacher_dashboard(p_class int, p_number int, p_name text)
returns jsonb language plpgsql security definer set search_path = '' stable as $$
declare result jsonb;
begin
  if not private.is_teacher(p_class, p_number, p_name) then
    raise exception '교사 정보를 확인해 주세요.' using errcode = '42501';
  end if;
  select jsonb_build_object('classes', coalesce(jsonb_agg(c.item order by c.class), '[]'::jsonb)) into result
  from (
    select s.class, jsonb_build_object(
      'class', s.class,
      'class_open', coalesce(st.exam_open, false),
      'exam_open', coalesce(st.exam_open, false),
      'students', jsonb_agg(jsonb_build_object(
        'number', s.number, 'student_id', s.student_id, 'grade', s.grade,
        'name', s.name, 'submission_id', sub.id, 'submitted_at', sub.submitted_at,
        'dialogue_ids', coalesce(sub.dialogue_ids, '{}'::text[]),
        'files', coalesce(sub.files, '{}'::text[]),
        'durations', coalesce(sub.durations, '{}'::numeric[]),
        'published_score', (
          select jsonb_build_object('final_score', score.final_score, 'dialogues', score.dialogues,
            'note', score.note, 'published_at', score.published_at)
          from public.published_scores score where score.class = s.class and score.number = s.number
        ),
        'practice_submissions', (
          select coalesce(jsonb_agg(jsonb_build_object(
            'id', practice.id, 'dialogue_id', practice.dialogue_id,
            'file', practice.file, 'submitted_at', practice.submitted_at
          ) order by practice.submitted_at desc, practice.id desc), '[]'::jsonb)
          from public.practice_submissions practice
          where practice.class = s.class and practice.number = s.number
        )
      ) order by s.number)
    ) as item
    from public.students s
    left join public.settings st on st.class = s.class
    left join public.submissions sub on sub.class = s.class and sub.number = s.number
    where not s.is_teacher
    group by s.class, st.exam_open
  ) c;
  return result;
end $$;
