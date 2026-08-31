"""Marketing sync — bi-directional sync between Supabase marketing.* and
~/.rowboat/knowledge/Marketing/People/ markdown files.

Modules:
  render_md   : pure-function Markdown renderer (Phase 2)
  _frontmatter: deterministic YAML frontmatter serialization
  _filename   : handle -> safe filename sanitization
  _queries    : SQL strings (centralised so trigger + render see same shape)
  _db         : thin psycopg/docker-exec wrapper for both worker contexts
  worker_db_to_fs : LISTEN on marketing_sync, render+write files (Phase 4)
  worker_fs_to_db : watchdog observer, propagates deletes back to DB (Phase 5)
"""
