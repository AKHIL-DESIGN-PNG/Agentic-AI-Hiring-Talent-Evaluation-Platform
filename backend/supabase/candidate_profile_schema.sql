create extension if not exists "pgcrypto";

create table if not exists public.candidate_profile_analysis (
  id uuid primary key default gen_random_uuid(),
  exam_invite_id text not null unique,
  candidate_email text not null,
  candidate_name text not null,
  github_score numeric not null default 0,
  leetcode_score numeric not null default 0,
  resume_score numeric not null default 0,
  profile_score numeric not null default 0,
  skills jsonb not null default '[]'::jsonb,
  parser_status text not null default 'pending',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_candidate_profile_analysis_email
  on public.candidate_profile_analysis (candidate_email);

create index if not exists idx_candidate_profile_analysis_exam_invite_id
  on public.candidate_profile_analysis (exam_invite_id);
