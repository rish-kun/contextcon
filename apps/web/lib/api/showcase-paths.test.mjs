import assert from "node:assert/strict";
import { test } from "node:test";
import { showcaseReadPath } from "./showcase-paths.ts";

test("case, run, thesis and investor reads go to the public showcase routes", () => {
  assert.equal(showcaseReadPath("GET", "/cases/abc"), "/public/showcase/case");
  assert.equal(showcaseReadPath("GET", "/cases/abc/assessments"), "/public/showcase/case/assessments");
  assert.equal(showcaseReadPath("GET", "/runs/r1"), "/public/showcase/runs/r1");
  assert.equal(
    showcaseReadPath("GET", "/runs/r1/activity?after=0&limit=500"),
    "/public/showcase/runs/r1/activity?after=0&limit=500",
  );
  assert.equal(showcaseReadPath("GET", "/theses/t1"), "/public/showcase/discovery");
  assert.equal(showcaseReadPath("GET", "/investor-searches/s1"), "/public/showcase/investors");
  assert.equal(showcaseReadPath("GET", "/policy"), "/policy");
});

test("everything else is refused: writes, lists, messages and file links", () => {
  for (const [method, path] of [
    ["POST", "/cases/abc/verify"],
    ["POST", "/cases/abc/claims"],
    ["POST", "/cases/abc/messages/m/send"],
    ["GET", "/cases"],
    ["GET", "/cases/abc/messages/send-summary"],
    ["GET", "/documents/d1/url"],
    ["GET", "/auth/me"],
    ["PUT", "/theses/t1/criteria"],
  ]) {
    assert.equal(showcaseReadPath(method, path), null, `${method} ${path}`);
  }
});
