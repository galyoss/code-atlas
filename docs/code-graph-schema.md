# Code graph schema

Version **1.0.0**.

Normative schema: `/cursor/stores/self/docs/code-graph-schema.json`

Synthetic instance: `/cursor/stores/self/docs/code-graph-example.json`

Real-repository instance: `/cursor/stores/self/docs/code-graph-example-aegra.json`

Every property and every enum value is described in the schema. This file is the map. Where they differ, the schema's `const` descriptions win.

## Purpose

An agent cannot take a whole repository. A scanner inventories HTTP routes, then for each route emits one security slice: the auth hooks that run for that request (including hooks defined in another file), the handler, and the callees that read or write data, with file and line evidence.

The agent judges one slice, or a small batch, at a time. The question the slice is built to answer is whether the object named by the request is tied to the identity in scope. The same document carries the identity, the object, and the fields a write assigns, so a later pass over auth bypass or mass assignment uses this schema rather than a second one.

The document is the code graph. Findings, severity, and fix text belong in a later layer. The slice is what makes those judgments possible.

The walk that produces a slice is the one described for this kind of review: map the definitions in each file, follow invocations into a call graph, and coalesce that graph into one small blob per route. Evidence stays as file and line ranges, in execution order, with an optional short excerpt.

## Top-level shape

One JSON document per repository.

| Field | Role |
| --- | --- |
| `schemaVersion` | Const `1.0.0` for this schema. |
| `illustrative` | `true` when a person wrote the document to show the shape. `false` when a scanner emitted it. |
| `note` | Required when `illustrative` is `true`. States that the document is a fixture. |
| `generator` | `name` and `version` of the program that wrote the document. |
| `repo` | `name`, `revision`, and `vcs` (`git`, `none`, `unknown`). Paths elsewhere are relative to this repository. |
| `languages` | Languages indexed: `python`, `ruby`, `javascript`, `typescript`. |
| `frameworks` | Frameworks on the routes: `rails`, `django`, `fastapi`, `express`, `nestjs`, `flask`, `sinatra`, `other`. |
| `generatedAt` | RFC 3339 timestamp. |
| `unresolvedGaps` | Surfaces the generator did not fully model. Empty means the generator claims no such gap. |
| `symbolIndex` | In-repo definitions the routes reference: id, language, kind, qualified name, one-line signature, file and lines. No file bodies. |
| `routes` | One slice per HTTP route. |

A judge for one route receives that `routes` item plus the `symbolIndex` entries it names. External callees have no index entry. Their calls use `resolution` `external` and a qualified name.

## Route slice

Each item of `routes` is the blob for one method and one path. A resource macro that expands to several actions becomes several items.

**Identity.** `httpMethod`, `pathTemplate`, `framework`, `language`, `handler` (`symbolId`, `qualifiedName`, file and lines), and `registration` (where the route is declared). `pathTemplate` is the external path after router prefixes are joined. Parameters use `{name}`. The root path is `/`. No trailing slash on any other path.

**Entry params.** Every request value the route reads, not only object ids. `location` is `path`, `query`, `body`, `header`, `cookie`, `form`, or `unknown`. Header names are lowercase. `namesObject` is `yes` when the value is used as a handle of a persisted object, `no` when the included uses were inspected and none are, `unknown` when the tracer could not tell. `reads` are the file and lines of each read.

**Identity in scope.** `identityBindings` lists principals the handler can see (`user`, `account`, `tenant`, `role`, `session`, `api_key`, `anonymous`, `unknown`). An empty array means no principal was found. `anonymous` is an explicit unauthenticated principal, which is a different fact.

**Auth chain.** Ordered hooks, including middleware, before-filters, guards, dependencies, decorators, policies, interceptors, and inline checks defined outside the handler file. Each step has a symbol, file and lines, `kind`, and either a snippet or the range the agent can read.

- `kind` `authentication` establishes or rejects a caller. That alone does not tie the caller to the object.
- `kind` `authorization` allows or denies an action, role, scope, or object.
- `kind` `unknown` was not classified.
- `bindsObjectToCaller` is `yes` only when the included source references both the caller and the object or an owner field. A dependency that only loads the user is `no`.
- `applicability` is `always`, `conditional`, or `unknown`.
- `onFailure` is `abort`, `continue`, or `unknown`. `continue` on an authentication step is the shape an auth-bypass review reads. The graph does not call it a finding.
- Framework auth hooks live here and are not repeated as `callGraph` roots. Calls inside an opened hook are nested on the step.

**Call graph.** A tree. Roots are the calls written in the handler. `children` are the calls written in an opened in-repo body. `order` is the execution sequence of every call node in the route, auth-step calls included, starting at 1 with no gaps. `depth` is 1 at a root and increases by one per child. `callSite` is the invocation, not the definition.

- `resolution` `resolved`: one in-repo definition, `symbolId` set.
- `resolution` `ambiguous`: not one in-repo definition. `candidates` lists the in-repo possibilities and is empty when the target is computed.
- `resolution` `external`: the body is outside the repository and is not inlined.
- `touchesPersistence` is `none`, `read`, `write`, `read_write`, or `unknown`.
- `expanded` `yes` means the child list is complete. `no` means the body was not opened and `children` is empty. `partial` means a `budget.omitted` entry points here.

**Data access.** The calls that load or mutate an application object. `operation` is `load`, `query`, `create`, `update`, or `delete`. `object` names the model and, when known, its symbol and table. `paramFlows` names which entry params reach which fields, with `confidence` `exact`, `probable`, or `unknown`. `callId` points at the call whose expression holds the predicate or the assignment, not at every wrapper around it. A commit is a call with `touchesPersistence` `write` and is a data access only when it names an object.

`ownershipEvidence` answers whether a caller or owner field is in the predicate. An owner field stores the principal an object belongs to (`owner_id`, `user_id`, `created_by`, `tenant_id`). The object's primary key is not an owner field. A filter on that primary key alone is `inPredicate` `no`.

| Value | `inPredicate` | `stampedOnWrite` |
| --- | --- | --- |
| `yes` | The included predicate references an owner field or an identity binding. `ownerFields` is non-empty. | A write assigns an owner field from an identity binding. |
| `no` | The tracer saw the predicate and it does not. | The tracer saw the assignments and no owner field comes from an identity binding. |
| `unknown` | The predicate was not visible. | The assignments were not visible. |
| `not_applicable` | The operation has no predicate. Creates use this. | The operation assigns no fields. Loads, queries, and deletes use this. |

`no` describes included source. It says nothing about code the slice dropped. Read `budget.coverage` before treating it as the whole route. A predicate that compares an owner field only to a client-supplied param is `inPredicate` `yes`, with that param in `paramFlows` and `identityBindingIds` empty.

`writtenFields` lists what a create or update assigns and where each value came from: `request_param`, `identity`, `loaded_object`, `constant`, or `unknown`. That list is the mass-assignment view. It is not a verdict.

**Related routes.** `relatedRoutes` points at other items in this document. `relations` are `same_model`, `same_path_prefix`, `same_handler_module`, and `shared_auth_symbol`. `sharedSymbolIds` names the symbols that justify the link. The link is how an agent contrasts two slices. It does not say which route checks ownership.

**Budget.** `limits` records `maxCallDepth`, `maxCallNodes`, and `maxSnippetChars` (at most 480, the schema cap). `counts` must match the route. `coverage` is `complete`, `partial`, or `unknown` for `authChain`, `callGraph`, and `dataFlow`. `omitted` lists what was dropped:

| Reason | Meaning |
| --- | --- |
| `depth` | The walk passed `maxCallDepth`. |
| `ambiguity` | The callee is `ambiguous` and its body was not inlined. |
| `node_budget` | The walk passed `maxCallNodes`. |
| `snippet_budget` | An excerpt was cut. This reason alone leaves coverage `complete`. |
| `external` | An out-of-repo callee was not recorded as a node. A node that is present, with its arguments, is not an omission. |
| `dynamic_dispatch` | The target is computed. The node's `resolution` is `ambiguous`. |
| `cycle` | The callee is already on the expansion path. |

`coverage` `complete` means the generator claims every in-scope in-repo body on that axis was included. A recorded external call is included context.

## How an agent reads one slice

Use the route and its symbols. Do not open the repository when the structured fields, and the snippets where the generator included them, are present. To contrast a neighbor, include that neighbor's route object from the same document.

1. Read `identityBindings` and `authChain`. A binding means a principal is in scope. `kind` `authentication` with `bindsObjectToCaller` `no` means the caller was identified and this hook did not compare them to the object. An empty chain with `coverage.authChain` `complete` means the generator found no hook.
2. Take `entryParams` whose `namesObject` is `yes`.
3. For each data access whose `paramFlows` cite those params, read `ownershipEvidence`. Also read `bindsObjectToCaller` on every auth step.
4. The included code ties the object to the caller when any included step or access is `yes`.
5. The included code does not tie them when every included site is `no`, all three coverage axes are `complete`, and no gap of `support` `partial` covers a surface this route uses. `unknown` stays unknown.
6. Open each `relatedRoutes` item and compare `ownershipEvidence` for `sharedSymbolIds`. The graph does not rank the two routes.
7. When coverage is `partial`, or a relevant gap is `partial`, the slice does not prove that a check is absent.

A later finding can name the method and path, the handler, the object-id param, the data access, the auth steps that ran, the neighbor that does constrain the owner, and a fix. Those sentences are not fields of this schema. The neighbor's predicate is what makes the fix concrete.

Evidence order for a human reading the slice: registration (binding time), then `authChain` in array order with each step's calls by `order`, then the handler range, then `callGraph` by `order`. Data-access snippets repeat the predicate or the assignment the agent has to see.

## Illustrative slice

`code-graph-example.json` is a hand-written fixture. `illustrative` is `true`. It is not a scan and it is not a vulnerability report. The code it describes is synthetic. The shape is the one this review uses as a running example: a route that creates a run on a thread.

Both routes authenticate with the same FastAPI dependency, `app.auth.deps.get_current_user` (lines 17–20), which requires a bearer token and aborts with 401 otherwise. The dependency does not take a thread id. `bindsObjectToCaller` is `no`. The principal in the handler is `user`.

`POST /threads/{thread_id}/runs` (`route_post_thread_runs`) calls `fetch_thread(db, thread_id)`. That helper loads the row by primary key:

```text
return db.query(Thread).filter(Thread.id == thread_id).one()
```

`da_load_thread` records `inPredicate` `no`, an empty `identityBindingIds`, and a flow of `path.thread_id` into `Thread.id` at confidence `exact`. The `Thread` symbol signature includes `owner_id`. The predicate does not use it. The route then inserts a `Run` with `thread_id` taken from the loaded row and `prompt` taken from the body. `stampedOnWrite` is `no`. Coverage on all three axes is `complete`, and `omitted` is empty, so the absence is about the included source.

`GET /threads/{thread_id}` (`route_get_thread`) uses the same dependency and a different predicate:

```text
return db.query(Thread).filter(Thread.id == thread_id, Thread.owner_id == user.id).one()
```

`da_get_thread` records `inPredicate` `yes`, `ownerFields` `["Thread.owner_id"]`, and `identityBindingIds` `["bind_get_user"]`.

Each route lists the other under `relatedRoutes` with `same_model`, `same_path_prefix`, and `shared_auth_symbol`, sharing `sym_thread` and `sym_get_current_user`. An agent compares those two ownership records. The document does not say which route is correct.

The fixture also declares three gaps: `graphql` and `websocket` as `unsupported`, and `dynamic_dispatch` as `partial` (ambiguous calls are recorded and not inlined; this fixture has none).

## Real repository slice

`/cursor/stores/self/docs/code-graph-example-aegra.json` is a second instance, hand-encoded from [aegra/aegra](https://github.com/aegra/aegra) tag `v0.11.0` (`46055c0b9adffe51fb168974f79dfadaa6edd612`). `illustrative` is `true` because a person wrote it from the source. It is not a scanner run and it is not a finding.

It contains two FastAPI routes from that tag:

- `POST /threads/{thread_id}/runs` (`aegra_api.api.runs.create_run`). The router depends on `require_auth`. The handler loads `Thread` with `where(ThreadORM.thread_id == thread_id)`, so that load's `inPredicate` is `no`. The next lines compare `existing_thread.user_id` to `user.identity` and raise 404; that comparison is an inline auth step with `bindsObjectToCaller` `yes`. `_prepare_run` later inserts `Run` with `user_id=user.identity` (`stampedOnWrite` `yes`) and loads `Assistant` with `user_id == user.identity` or `user_id == "system"` (`inPredicate` `yes`).
- `GET /threads/{thread_id}` (`aegra_api.api.threads.get_thread`). The same auth dependency runs. The load's predicate is `thread_id` and `user_id == user.identity`, so `inPredicate` is `yes`.

Both paths are in `SELF_DISPATCHING`, so `apply_auth_enforcement` does not attach a second `handle_event`. The routes call `handle_event` themselves, and that call invokes a handler registered at runtime. Those calls are `resolution` `ambiguous` with empty `candidates`. `budget.coverage` is `partial` on every axis, and `unresolvedGaps` records `dynamic_dispatch` as `partial`. A judge uses the included predicates and the inline comparison, and does not treat the slice as the whole program.

## Versioning

`schemaVersion` is semantic versioning. This schema file accepts only the const `1.0.0`. Consumers read `schemaVersion` and then validate. A document from a later version is not checked against this file.

- **Major.** A field is removed or renamed, a required set changes, or an enum value changes meaning.
- **Minor.** An optional field or an enum value is added. `additionalProperties` is false, and unknown enum values fail. A minor document does not validate against an older schema. Consumers refuse it rather than guess.
- **Patch.** Wording only. `schemaVersion` stays `1.0.0`. Instances do not change.

Do not reuse an enum value for a new meaning. Add a value and bump the minor version.

## Non-goals

- Findings, SARIF, severity, verdicts, and fix text.
- GraphQL operations and resolvers as routes. The HTTP handler that serves GraphQL may be a route. Its resolvers are not in the call graph. Declare `unresolvedGaps` kind `graphql`.
- WebSocket handlers as routes. Declare kind `websocket`.
- Resolving dynamic dispatch. Computed targets stay `resolution` `ambiguous` and are declared with kind `dynamic_dispatch`. This version does not pick a target.
- A whole-program graph. Each slice is one route, bounded by `budget.limits`.
- A proof of taint. `confidence` is the tracer's claim (`exact`, `probable`, `unknown`).
- Languages other than Python, Ruby, JavaScript, and TypeScript.
- Inlining library bodies. An external call keeps its arguments and its persistence effect. The body stays outside the slice.
- Replacing a snippet with a full file, or the reverse. Prefer ids and ranges. A snippet is optional and at most 480 characters.

## Invariants the schema does not check

A validator enforces the shape. A generator also keeps these true:

- Every `id` is unique in the document.
- Every `symbolId`, `routeId`, `callId`, entry-param id, and binding id refers to an object in the document.
- `symbolIndex` is exactly the definitions the routes reference.
- `budget.counts` matches the route, including nested call nodes and snippet objects.
- Call `order` is `1..N` with no gaps. A child's `order` is greater than its parent's, and its `depth` is the parent's depth plus one.
- `handler.range` and `handler.qualifiedName` match the symbol. An auth step matches its symbol range, except an `inline` step, whose range is the check and may sit inside the enclosing symbol.
- `endLine` is greater than or equal to `startLine`.
- `frameworks` equals the set of `route.framework`. `languages` includes every route language.
- `relatedRoutes` does not point at the route that holds it.
- When an axis is `complete`, the route has no omission other than `snippet_budget` on that axis, and every in-scope in-repo body is `expanded` `yes`.
- `pathTemplate` uses `{param}` placeholders, including joined router prefixes.
