"""Memo (CP-25): the finished case. Drafted, cited prose is stored with each assessment
version (`drafting`); structured sections, the source record, cost and retention are
built when the case is read. `app.pipelines.memo.detail` registers those sections of
`GET /cases/{id}` on `app.api.cases_sections` (imported by `app.api.cases`)."""
