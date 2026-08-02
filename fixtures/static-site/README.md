# Local static test target

A deterministic multi-page site served by nginx inside the compose stack, so
automation runs do not depend on a third party staying up.

This exists because a governed run against an external site was blocked for a
whole session by that site's outage — and, worse, an outage mid-run is hard to
tell apart from an application defect. A fixture you control removes the
ambiguity: a failure here is a real failure.

## Reachable at

| From | URL |
|---|---|
| Your browser | <http://localhost:8080/> |
| backend / worker containers | `http://static-test/` |
| spawned runner containers | `http://static-test/` |

## Networking

The runner container is attached to a dedicated `stlc_test_targets` network,
**not** the compose default. That is deliberate. Putting untrusted
LLM-generated test code on the application network would hand it Postgres,
Redis, the backend and the runner-executor by hostname — undoing the isolation
the executor split was built for.

`static-test` is the only service on both networks, so it is reachable from the
platform *and* from the sandbox, while the sandbox still cannot see anything
else internal. Internet egress is unaffected (a user-defined bridge NATs out),
so tests can still reach real external sites when that is the intent.

Set by `AUTOMATION_DOCKER_NETWORK=stlc_test_targets` in `.env`.

## Why the markup looks like this

The pages are shaped to match the approved Application Model for the
`WebApp` application (screens `home_page`/`about_page`/`services_page`/
`contact_page`, components `header_navigation`/`main_content`/`footer`/
`contact_form`), so an existing model stays valid against it.

Two constraints are load-bearing and easy to break by accident:

- **`<main aria-label="main">`** — the compiler emits
  `getByRole('main', { name: 'main', exact: true })`. A `<main>` with no
  accessible name will not match it.
- **Each nav word appears exactly once per page.** The compiler emits
  `getByText('Home')`, and Playwright's strict mode fails a locator that
  resolves to more than one element. This is why the headings read "Who We Are"
  and "What We Offer" rather than "About Us" and "Our Services".

The footer links carry `href="#"` on purpose. They are inert by design and
exercise the placeholder-link handling: a link the markup points nowhere is an
observed fact to record, not missing information to block on.
