# legacy-brain test/train scripts

Ad-hoc scripts relocated here on 2026-08-06 from `security/` root, where they had been
dumped despite having nothing to do with the security lab. They exercise the Brain
(Tahlamus) router, the space/bridge routing, and a few live integrations (mailcow SMTP,
groq, video workflow).

They are kept as-is for reference. Not wired into CI. Some rely on live services
(Bridge, Brain gateway, SMTP) and will fail offline. Prune once superseded by the
maintained brain/space test suites.
