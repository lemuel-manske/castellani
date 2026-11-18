# ADR-0025: URL identity, navigation scope, and crawl depth

- Status: Accepted
- Date: 2026-11-18

## Context

Several Capture replicas discover links concurrently. ADR-0013 requires deterministic run-scoped URL admission, deduplication, and depth limits, but a URL's spelling is not sufficient proof of its semantic equivalence with another URL. Over-aggressive canonicalization risks silently omitting archival evidence. Hash-routed browser applications also distinguish navigational states that share one HTTP resource.

Opportunistic crawling can discover a page through a long path before discovering a shorter one. The frontier therefore cannot equate first-discovered depth with minimum reachable depth.

## Decision

### Identities and normalization

Distinguish the **discovery URL** (the original link, retained for provenance), **HTTP fetch identity** (conservatively normalized HTTP(S) URL without an ordinary fragment), **crawl navigation identity** (fetch identity plus a recognized client-side hash route, if present), and **snapshot identity** (immutable historical capture identity). Within one archive run, an atomically admitted frontier task is keyed by its crawl navigation identity; distinct archive runs may recapture the same URL.

Apply deterministic, versioned normalization to HTTP(S) URLs:

- Lowercase scheme and hostname; normalize host serialization consistently.
- Remove default HTTP/HTTPS ports, resolve dot segments, normalize an empty HTTP path to `/`, and normalize percent-encoding only where URI equivalence is safe (including unreserved characters).
- **Preserve path case and nonempty trailing slashes**. `/course` and `/course/` are distinct; `https://example.com` and `https://example.com/` share the normalized root path.
- Preserve query strings, parameter ordering, repeated keys, and values. Do not remove tracking parameters or sort queries by default.
- Preserve the original requested/discovered URL and redirect chain as provenance. Redirect destinations and `rel=canonical` hints are metadata, not automatic grounds for merging independently admitted tasks.
- Do not conflate `http` and `https`, and do not use response-content similarity as a frontier identity rule.

For ordinary fragments such as `#introduction` and `#conclusion`, ignore the fragment in HTTP fetch and crawl-task identity while retaining it in provenance. Fragments beginning with `/` or `!/` are recognized as **potential client-side hash routes** regardless of where the `#` occurs in the path (for example, `/#/settings` and `/app#/dashboard`). Preserve those route fragments in the *navigation* task key and navigate with the browser; they still do not identify separate HTTP network resources. This is an explicit heuristic, not a universal URL-equivalence standard; site-specific exceptions may be added later.

The URL identity algorithm and hash-route policy are fixed for the duration of a run. Changing them requires a new policy version rather than silently changing existing frontier keys.

### Scope and resource discovery

Distinguish navigational documents from embedded resources and downloads. By default, navigational links remain within the seed's HTTP origin unless the run's explicitly configured scope allows other origins. A path-prefix restriction is **not** implied by the seed URL: Moodle-style course and assignment paths may be unrelated. Scope is evaluated on redirect destinations as well as discovered links, and network safety controls apply to every fetch.

Embedded assets required for replay (for example CSS, images, fonts, and scripts) and linked downloadable attachments follow explicit resource policies rather than consuming ordinary navigational depth or page-count slots by default. Their retrieval is still bounded by origin/authorization rules, size limits, and resource budgets; an off-origin asset is not unconditionally allowed merely because the referring document uses it. Exact site-specific attachment classification and budgets are configurable capture policy.

### Depth and concurrent discovery

The seed has depth 0; following an admitted **navigational** link increments depth by one, including links between distinct hash routes. Embedded resources and associated attachments do not create an extra navigational hop.

The frontier atomically retains the **minimum discovered depth** for each navigation identity. A duplicate discovery never creates another logical page task. If a later shorter path makes further traversal eligible, the frontier must make previously skipped descendant-discovery work eligible or otherwise re-evaluate recorded outgoing links, without recapturing an already committed snapshot solely to adjust its depth. A page may be captured before its final minimum depth is known.

Any required re-evaluation is durably accounted for before crawl termination; page-limit admission and finalization remain atomic under ADR-0013. Exact link-graph persistence and depth-correction algorithms are implementation details.

## Consequences

Conservative normalization favors preserving distinct archival content over eliminating every redundant fetch. Hash-routed applications can produce multiple browser navigation captures for a shared HTTP document. Run-scoped versioned identities make conditional DynamoDB admission consistent across replicas.

Minimum-depth correction may require retaining extracted link edges and repeating discovery evaluation, adding storage and coordination work. URL normalization does not replace redirects, crawl scope enforcement, or authentication-context isolation. Multi-account capture of the same URL within one run is not supported by URL identity alone and would require an explicit extension.
