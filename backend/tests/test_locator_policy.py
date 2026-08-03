from app.agents.automation.generation_contract import AutomationGenerationContract
from app.services.script_compiler import locator_policy


def test_rank_orders_role_above_xpath():
    assert locator_policy.rank("role") < locator_policy.rank("xpath")
    assert locator_policy.rank("label") < locator_policy.rank("css")


def test_is_preferred_over():
    assert locator_policy.is_preferred_over("role", "css") is True
    assert locator_policy.is_preferred_over("xpath", "role") is False


def test_requires_exception_flags_css_and_xpath_only():
    assert locator_policy.requires_exception("css") is True
    assert locator_policy.requires_exception("xpath") is True
    assert locator_policy.requires_exception("role") is False
    assert locator_policy.requires_exception("testid") is False


def test_unknown_strategy_ranks_last():
    assert locator_policy.rank("unknown_strategy") == len(locator_policy.LOCATOR_PRIORITY)


def test_render_locator_playwright_all_strategies():
    assert locator_policy.render_locator_playwright("role", "Sign in", "button") == \
        "page.getByRole('button', { name: 'Sign in', exact: true })"
    assert locator_policy.render_locator_playwright("label", "Username") == "page.getByLabel('Username')"
    assert locator_policy.render_locator_playwright("placeholder", "Search") == "page.getByPlaceholder('Search')"
    assert locator_policy.render_locator_playwright("text", "Welcome") == "page.getByText('Welcome')"
    assert locator_policy.render_locator_playwright("testid", "order-id") == "page.getByTestId('order-id')"
    assert locator_policy.render_locator_playwright("css", "#foo") == "page.locator('#foo')"
    assert locator_policy.render_locator_playwright("xpath", "//div") == "page.locator('xpath=//div')"


def test_render_locator_playwright_rejects_unknown_strategy():
    import pytest
    with pytest.raises(ValueError):
        locator_policy.render_locator_playwright("nonsense", "x")


def test_render_locator_playwright_escapes_single_quotes_in_css_selector():
    # A live run produced `page.locator('input[name='q']')` — a CSS
    # attribute selector's own single quotes (very common: [attr='value']
    # syntax) terminated the string literal early, breaking the compiled
    # TypeScript with a syntax error.
    rendered = locator_policy.render_locator_playwright("css", "input[name='q']")
    assert rendered == "page.locator('input[name=\\'q\\']')"
    # Sanity: the escaped result round-trips back through the parser.
    assert locator_policy.parse_locator_playwright(rendered) == ("css", "input[name='q']", None, None)


def test_render_locator_playwright_escapes_single_quotes_in_role_name():
    rendered = locator_policy.render_locator_playwright("role", "Don't submit", "button")
    assert rendered == "page.getByRole('button', { name: 'Don\\'t submit', exact: true })"
    assert locator_policy.parse_locator_playwright(rendered) == ("role", "Don't submit", "button", None)


def test_render_locator_playwright_escapes_backslashes():
    rendered = locator_policy.render_locator_playwright("css", "a\\b")
    assert rendered == "page.locator('a\\\\b')"


def test_render_locator_pytest_role_uses_snake_case_api():
    assert locator_policy.render_locator_pytest("role", "Sign in", "button") == \
        "page.get_by_role('button', name='Sign in', exact=True)"
    assert locator_policy.render_locator_pytest("testid", "order-id") == "page.get_by_test_id('order-id')"


def test_render_locator_pytest_escapes_single_quotes_in_css_selector():
    rendered = locator_policy.render_locator_pytest("css", "input[name='q']")
    assert rendered == "page.locator('input[name=\\'q\\']')"


def test_parse_locator_playwright_inverts_render_for_all_strategies():
    cases = [
        ("role", "Sign in", "button"),
        ("label", "Username", None),
        ("placeholder", "Search", None),
        ("text", "Welcome", None),
        ("testid", "order-id", None),
        ("css", "#foo", None),
        ("xpath", "//div", None),
    ]
    for strategy, value, role_hint in cases:
        rendered = locator_policy.render_locator_playwright(strategy, value, role_hint)
        parsed = locator_policy.parse_locator_playwright(rendered)
        assert parsed == (strategy, value, role_hint, None), f"round-trip failed for {strategy}"


def test_parse_locator_playwright_handles_non_ascii_and_unicode_names():
    rendered = locator_policy.render_locator_playwright("role", "بحث", "combobox")
    assert locator_policy.parse_locator_playwright(rendered) == ("role", "بحث", "combobox", None)


def test_parse_locator_playwright_handles_role_without_name():
    assert locator_policy.parse_locator_playwright("page.getByRole('button')") == ("role", "", "button", None)


def test_parse_locator_playwright_returns_none_for_unrecognized_string():
    assert locator_policy.parse_locator_playwright("someRandomExpression()") is None


# ── .nth() disambiguation — a live run failed with a Playwright "strict mode
# violation": two identically-named "Show password" buttons on one page
# collapsed to a single non-unique locator at runtime. ──────────────────────

def test_render_locator_playwright_appends_nth_suffix():
    rendered = locator_policy.render_locator_playwright("role", "Show password", "button", nth=1)
    assert rendered == "page.getByRole('button', { name: 'Show password', exact: true }).nth(1)"


def test_render_locator_playwright_omits_nth_suffix_when_none():
    rendered = locator_policy.render_locator_playwright("role", "Show password", "button", nth=None)
    assert ".nth(" not in rendered


def test_parse_locator_playwright_round_trips_nth_suffix():
    rendered = locator_policy.render_locator_playwright("role", "Show password", "button", nth=1)
    assert locator_policy.parse_locator_playwright(rendered) == ("role", "Show password", "button", 1)


def test_parse_locator_playwright_nth_suffix_works_for_non_role_strategies():
    rendered = locator_policy.render_locator_playwright("css", ".toggle", nth=2)
    assert rendered == "page.locator('.toggle').nth(2)"
    assert locator_policy.parse_locator_playwright(rendered) == ("css", ".toggle", None, 2)


def test_ground_page_object_elements_propagates_nth_from_catalog():
    """The force-override path (grounding) must copy nth from the catalog
    entry, not just strategy/value/role_hint — otherwise a disambiguated
    catalog entry still compiles to an ambiguous locator."""
    contract = _contract_with_element("button_show_password_2", "role", "Show password", "button")
    catalog = [{
        "element_name": "button_show_password_2",
        "recommended_locator": "page.getByRole('button', { name: 'Show password', exact: true }).nth(1)",
    }]

    locator_policy.ground_page_object_elements(contract, catalog)

    element = contract.page_objects[0].elements[0]
    assert element.nth == 1


def test_ground_page_object_elements_sets_nth_none_when_catalog_entry_has_none():
    contract = _contract_with_element("combobox", "role", "combobox", "search")
    contract.page_objects[0].elements[0].nth = 3  # stale value from a prior grounding pass
    catalog = [{"element_name": "combobox", "recommended_locator": "page.getByRole('combobox', { name: 'بحث' })"}]

    locator_policy.ground_page_object_elements(contract, catalog)

    assert contract.page_objects[0].elements[0].nth is None


# ── ground_page_object_elements: real bug found via a live run — the LLM
# named an element after a discovered one ("combobox") but swapped its ARIA
# role and accessible name between roleHint/locatorValue, producing a
# locator that matched nothing on the real page despite the correct name ──

def _contract_with_element(name: str, strategy: str, value: str, role_hint: str | None):
    from app.agents.automation.generation_contract import AutomationGenerationContract
    return AutomationGenerationContract.model_validate({
        "contractVersion": "1.0", "testCaseId": "TC-1", "scriptType": "playwright-typescript",
        "pageObjects": [{"name": "SearchPage", "elements": [{
            "name": name, "locatorStrategy": strategy, "locatorValue": value, "roleHint": role_hint,
        }]}],
    })


def test_ground_page_object_elements_overrides_mistranscribed_fields():
    # LLM swapped role_hint="search" / locatorValue="combobox" — should have
    # been role_hint="combobox" / locatorValue="بحث" per the catalog.
    contract = _contract_with_element("combobox", "role", "combobox", "search")
    catalog = [{
        "element_name": "combobox",
        "recommended_locator": "page.getByRole('combobox', { name: 'بحث' })",
    }]

    locator_policy.ground_page_object_elements(contract, catalog)

    element = contract.page_objects[0].elements[0]
    assert element.locator_strategy == "role"
    assert element.locator_value == "بحث"
    assert element.role_hint == "combobox"


def test_ground_page_object_elements_leaves_unmatched_elements_alone():
    contract = _contract_with_element("mysteryButton", "role", "guess", "button")
    catalog = [{"element_name": "combobox", "recommended_locator": "page.getByRole('combobox', { name: 'بحث' })"}]

    locator_policy.ground_page_object_elements(contract, catalog)

    element = contract.page_objects[0].elements[0]
    assert element.locator_value == "guess"  # untouched — no name match in catalog


def test_ground_page_object_elements_noop_when_catalog_empty():
    contract = _contract_with_element("combobox", "role", "combobox", "search")
    locator_policy.ground_page_object_elements(contract, None)
    locator_policy.ground_page_object_elements(contract, [])
    element = contract.page_objects[0].elements[0]
    assert element.locator_value == "combobox"  # untouched


# ── ground_page_object_elements: single-candidate fill-step fallback — a
# harder failure mode confirmed via three consecutive live regenerations of
# the same test case, where the LLM never reused the catalog's element name
# OR locator at all ("searchBar"/input[name='q'], then an unnamed
# searchBox, then "searchInput"/getByPlaceholder('Search')), so
# name-matching alone never triggered. ──────────────────────────────────────

def _contract_with_fill_step(element_name: str, strategy: str, value: str, role_hint: str | None = None):
    from app.agents.automation.generation_contract import AutomationGenerationContract
    return AutomationGenerationContract.model_validate({
        "contractVersion": "1.0", "testCaseId": "TC-1", "scriptType": "playwright-typescript",
        "pageObjects": [{"name": "SearchPage", "elements": [{
            "name": element_name, "locatorStrategy": strategy, "locatorValue": value, "roleHint": role_hint,
        }]}],
        "steps": [{"phase": "act", "action": "fill", "target": f"SearchPage.{element_name}", "dataBinding": "q"}],
    })


def test_ground_page_object_elements_grounds_unmatched_fill_target_via_single_text_input_candidate():
    contract = _contract_with_fill_step("searchInput", "placeholder", "Search")
    catalog = [
        {"element_name": "combobox", "recommended_locator": "page.getByRole('combobox', { name: 'بحث' })"},
        {"element_name": "link_gmail", "recommended_locator": "page.getByRole('link', { name: 'Gmail' })"},
    ]

    locator_policy.ground_page_object_elements(contract, catalog)

    element = contract.page_objects[0].elements[0]
    assert element.locator_strategy == "role"
    assert element.locator_value == "بحث"
    assert element.role_hint == "combobox"


def test_ground_page_object_elements_skips_fallback_when_multiple_text_input_candidates():
    contract = _contract_with_fill_step("searchInput", "placeholder", "Search")
    catalog = [
        {"element_name": "combobox", "recommended_locator": "page.getByRole('combobox', { name: 'بحث' })"},
        {"element_name": "textbox_email", "recommended_locator": "page.getByRole('textbox', { name: 'Email' })"},
    ]

    locator_policy.ground_page_object_elements(contract, catalog)

    element = contract.page_objects[0].elements[0]
    assert element.locator_value == "Search"  # untouched — ambiguous, no single candidate


def test_ground_page_object_elements_fallback_does_not_override_a_name_match():
    contract = _contract_with_fill_step("combobox", "role", "combobox", "search")
    catalog = [
        {"element_name": "combobox", "recommended_locator": "page.getByRole('combobox', { name: 'بحث' })"},
    ]

    locator_policy.ground_page_object_elements(contract, catalog)

    element = contract.page_objects[0].elements[0]
    assert element.role_hint == "combobox"
    assert element.locator_value == "بحث"


def test_ground_page_object_elements_fallback_ignores_non_fill_steps():
    from app.agents.automation.generation_contract import AutomationGenerationContract
    contract = AutomationGenerationContract.model_validate({
        "contractVersion": "1.0", "testCaseId": "TC-1", "scriptType": "playwright-typescript",
        "pageObjects": [{"name": "SearchPage", "elements": [{
            "name": "searchInput", "locatorStrategy": "placeholder", "locatorValue": "Search",
        }]}],
        "steps": [{"phase": "act", "action": "click", "target": "SearchPage.searchInput"}],
    })
    catalog = [{"element_name": "combobox", "recommended_locator": "page.getByRole('combobox', { name: 'بحث' })"}]

    locator_policy.ground_page_object_elements(contract, catalog)

    element = contract.page_objects[0].elements[0]
    assert element.locator_value == "Search"  # untouched — not a fill step


# ── filter_catalog_by_page: real bug found via a live run — TC-0110's
# generated page object grounded its "search box" against an
# accounts.google.com sign-in field pulled from the same application's
# locator_map catalog, which spans both google.com and accounts.google.com.
# That element doesn't exist on the page the test actually visits, so the
# "grounded: true" result was a false positive. ─────────────────────────────

_CROSS_HOST_CATALOG = [
    {"element_name": "combobox", "page": "https://www.google.com/",
     "recommended_locator": "page.getByRole('combobox', { name: 'بحث' })"},
    {"element_name": "link_gmail", "page": "https://www.google.com/",
     "recommended_locator": "page.getByRole('link', { name: 'Gmail' })"},
    {"element_name": "textbox_email_or_phone", "page": "https://accounts.google.com/v3/signin/identifier",
     "recommended_locator": "page.getByRole('textbox', { name: 'Email or phone' })"},
]


def test_filter_catalog_by_page_excludes_entries_from_a_different_host():
    scoped = locator_policy.filter_catalog_by_page(_CROSS_HOST_CATALOG, "https://www.google.com/")
    assert {e["element_name"] for e in scoped} == {"combobox", "link_gmail"}


def test_filter_catalog_by_page_falls_back_to_full_catalog_when_nothing_matches():
    scoped = locator_policy.filter_catalog_by_page(_CROSS_HOST_CATALOG, "https://example.com/")
    assert scoped == _CROSS_HOST_CATALOG


def test_filter_catalog_by_page_returns_catalog_unchanged_without_a_base_url():
    assert locator_policy.filter_catalog_by_page(_CROSS_HOST_CATALOG, None) == _CROSS_HOST_CATALOG


def test_filter_catalog_by_page_passes_through_empty_catalog():
    assert locator_policy.filter_catalog_by_page([], "https://www.google.com/") == []
    assert locator_policy.filter_catalog_by_page(None, "https://www.google.com/") is None


# ── check_url_targets_grounded — the navigation counterpart of element
# grounding (Playwright AI Studio, added after a live run where 3/6 scripts
# failed on LLM-invented destination patterns like '/candidate' when the
# real explored page was '/sign-up?role=candidate'). ────────────────────────

def _contract(steps=None, assertions=None):
    return AutomationGenerationContract.model_validate({
        "contractVersion": "1.0", "testCaseId": "TC-1", "testType": "functional",
        "scriptType": "playwright-typescript", "environmentProfile": "SIT",
        "businessFlow": "x", "preconditions": [], "testDataBindings": [],
        "pageObjects": [{
            "name": "Home", "route": "/",
            "elements": [{"name": "button", "locatorStrategy": "role", "locatorValue": "Go", "roleHint": "button"}],
        }],
        "steps": steps or [], "expectedResults": [],
        "assertions": assertions or [], "apiValidations": [], "dbValidations": [],
        "cleanupActions": [], "evidenceRequired": [],
    })


_EXPLORED = [
    "https://rankix.ai/",
    "https://rankix.ai/sign-up?role=candidate",
    "https://rankix.ai/sign-up?role=employer",
]


def test_check_url_targets_grounded_flags_invented_wait_for_url():
    contract = _contract(steps=[
        {"phase": "act", "action": "wait_for_url", "value": "/candidate"},
    ])
    ungrounded = locator_policy.check_url_targets_grounded(contract, _EXPLORED)
    assert ungrounded == ["wait_for_url:/candidate"]


def test_check_url_targets_grounded_accepts_real_pattern():
    contract = _contract(steps=[
        {"phase": "act", "action": "wait_for_url", "value": "role=candidate"},
    ])
    assert locator_policy.check_url_targets_grounded(contract, _EXPLORED) == []


def test_check_url_targets_grounded_checks_url_assertions_too():
    contract = _contract(assertions=[
        {"type": "url", "target": "page", "expected": "employer-signup"},
    ])
    ungrounded = locator_policy.check_url_targets_grounded(contract, _EXPLORED)
    assert ungrounded == ["url_assertion:employer-signup"]


def test_check_url_targets_grounded_ignores_non_url_steps():
    contract = _contract(
        steps=[{"phase": "act", "action": "click", "target": "Home.button"}],
        assertions=[{"type": "visible", "target": "Home.button", "expected": "true"}],
    )
    assert locator_policy.check_url_targets_grounded(contract, _EXPLORED) == []


def test_check_url_targets_grounded_no_op_without_explored_paths():
    """Regular (non-Studio) test cases carry no explored_page_paths — silence,
    not a false positive, when there's nothing real to check against."""
    contract = _contract(steps=[{"phase": "act", "action": "wait_for_url", "value": "/totally-invented"}])
    assert locator_policy.check_url_targets_grounded(contract, None) == []
    assert locator_policy.check_url_targets_grounded(contract, []) == []


# ── Rendered-locator recovery ─────────────────────────────────────────────────
# Regression cover for 8 live failures where the LLM put an already-rendered
# locator into `locatorValue`. The renderer escaped it into an accessible name,
# producing getByRole('link', { name: "page.getByRole('link', ...)" }) — a
# locator that cannot match anything and times out 15s later blaming the page.


def test_nested_rendered_locator_is_recovered_not_embedded():
    nested = "page.getByRole('link', { name: 'Dashboard', exact: true })"
    rendered = locator_policy.render_locator_playwright("role", nested, "button")
    assert rendered == "page.getByRole('link', { name: 'Dashboard', exact: true })"
    # The give-away of the old bug: the expression nested inside a name.
    assert "name: 'page.getByRole" not in rendered


def test_recovered_role_hint_overrides_the_wrong_one():
    """The nested expression is authoritative — it is what discovery validated."""
    nested = "page.getByRole('link', { name: 'Dashboard', exact: true })"
    assert "getByRole('link'" in locator_policy.render_locator_playwright("role", nested, "button")


def test_recovery_carries_the_nested_nth():
    nested = "page.getByRole('button', { name: 'Sign in', exact: true }).nth(2)"
    assert locator_policy.render_locator_playwright("role", nested, "link").endswith(".nth(2)")


def test_explicit_nth_wins_over_the_recovered_one():
    nested = "page.getByRole('button', { name: 'Sign in', exact: true }).nth(2)"
    assert locator_policy.render_locator_playwright("role", nested, "link", 0).endswith(".nth(0)")


def test_recovery_handles_every_rendered_strategy():
    for nested, expected in [
        ("page.getByPlaceholder('name@company.com')", "page.getByPlaceholder('name@company.com')"),
        ("page.getByLabel('Email')", "page.getByLabel('Email')"),
        ("page.getByTestId('submit')", "page.getByTestId('submit')"),
        ("page.getByText('Sign in')", "page.getByText('Sign in')"),
    ]:
        assert locator_policy.render_locator_playwright("role", nested, "button") == expected


def test_genuine_name_containing_parentheses_is_untouched():
    """Must not over-trigger: real accessible names contain punctuation."""
    rendered = locator_policy.render_locator_playwright("role", "Notifications (F8)", "button")
    assert rendered == "page.getByRole('button', { name: 'Notifications (F8)', exact: true })"


def test_plain_values_are_unaffected():
    assert (
        locator_policy.render_locator_playwright("placeholder", "name@company.com")
        == "page.getByPlaceholder('name@company.com')"
    )
    # Built rather than written as a literal, so the assertion is not a puzzle
    # about how many backslashes survive the source encoding. A CSS selector's
    # own single quotes must come out escaped for the JS string literal.
    expected_css = "page.locator('input[name=" + chr(92) + "'q" + chr(92) + "']')"
    assert locator_policy.render_locator_playwright("css", "input[name='q']") == expected_css


def test_unparseable_rendered_locator_fails_at_compile_time():
    """It cannot be a real accessible name either, so failing loudly beats
    emitting a script guaranteed to time out."""
    import pytest

    with pytest.raises(ValueError, match="rendered locator expression"):
        locator_policy.render_locator_playwright("role", "page.getByRole(totally broken", "button")


def test_round_trip_is_stable():
    """Rendering a recovered locator again must not change it."""
    original = "page.getByRole('link', { name: 'Dashboard', exact: true })"
    once = locator_policy.render_locator_playwright("role", original, "button")
    twice = locator_policy.render_locator_playwright("role", once, "button")
    assert once == twice == original


# ── catalog selection for the generation prompt ───────────────────────────────
# Measured on project 8: 157 entries rendered 25,399 characters around a
# 1,100-character test case — 97% of the prompt was locators. Every call was
# ~8k tokens, which is slow on a local model and what exhausted its context
# when several ran concurrently.

def _entry(name, *, confidence=50, meaning=None):
    return {
        "element_name": name, "business_meaning": meaning,
        "recommended_locator": f"page.getByRole('link', {{ name: '{name}' }})",
        "confidence_score": confidence, "page": "https://app.example.com/",
    }


def test_a_catalog_within_the_limit_is_returned_untouched():
    catalog = [_entry(f"button_{i}") for i in range(10)]
    assert locator_policy.select_relevant_catalog(catalog, "anything", limit=60) is catalog


def test_entries_named_in_the_test_case_are_kept_first():
    catalog = [_entry(f"filler_{i}") for i in range(80)]
    catalog.append(_entry("button_submit_application"))
    catalog.append(_entry("input_candidate_email"))

    selected = locator_policy.select_relevant_catalog(
        catalog, "Submit the application after entering the candidate email", limit=5,
    )

    names = [e["element_name"] for e in selected]
    assert "button_submit_application" in names
    assert "input_candidate_email" in names


def test_the_cap_is_honoured():
    catalog = [_entry(f"filler_{i}") for i in range(200)]
    assert len(locator_policy.select_relevant_catalog(catalog, "login", limit=60)) == 60


def test_unmentioned_controls_still_fill_the_cap_by_confidence():
    """A login test rarely names its submit button in the steps. Dropping every
    unmentioned control would strand exactly the elements the flow needs."""
    catalog = [_entry(f"filler_{i}", confidence=10) for i in range(100)]
    catalog.append(_entry("button_continue", confidence=99))

    selected = locator_policy.select_relevant_catalog(catalog, "unrelated words here", limit=3)

    assert len(selected) == 3
    assert "button_continue" in [e["element_name"] for e in selected]


def test_selection_is_deterministic_for_the_same_inputs():
    """The prompt feeds an idempotency hash — an unstable order would make the
    same request look like a different one on every retry."""
    catalog = [_entry(f"item_{i}", confidence=i % 7) for i in range(120)]
    first = locator_policy.select_relevant_catalog(catalog, "item_9 and item_40", limit=20)
    second = locator_policy.select_relevant_catalog(catalog, "item_9 and item_40", limit=20)
    assert [e["element_name"] for e in first] == [e["element_name"] for e in second]


def test_a_non_empty_catalog_never_selects_down_to_nothing():
    """An unfiltered prompt is slow; a prompt with no locators is ungrounded,
    which is worse."""
    catalog = [_entry(f"item_{i}") for i in range(100)]
    assert locator_policy.select_relevant_catalog(catalog, "", limit=5)


# ── hash-routed SPAs ──────────────────────────────────────────────────────────
# Observed live 2026-08-03: an Angular app served every route from
# https://site/client/#/auth/login. Dropping the fragment explored it as
# "/client/", so a contract asserting on the real URL was reported ungrounded
# and blocked from execution — with "regenerate before running" advice that
# could never work, because regeneration produces the same correct URL.

def test_explored_paths_keep_the_fragment():
    assert locator_policy._explored_paths(
        ["https://rahulshettyacademy.com/client/#/auth/login"]
    ) == ["/client/#/auth/login"]


def test_explored_paths_keep_query_and_fragment_together():
    assert locator_policy._explored_paths(
        ["https://site/app?role=employer#/step/2"]
    ) == ["/app?role=employer#/step/2"]


def test_a_hash_route_assertion_is_grounded_against_its_own_page():
    contract = AutomationGenerationContract.model_validate({
        "contractVersion": "1.0", "testCaseId": "TC-0085",
        "scriptType": "playwright-typescript", "businessFlow": "Invalid login",
        "pageObjects": [],
        "assertions": [{"type": "url", "target": "page", "expected": "/client/#/auth/login"}],
    })

    assert locator_policy.check_url_targets_grounded(
        contract, ["https://rahulshettyacademy.com/client/#/auth/login"]
    ) == []


def test_an_invented_hash_route_is_still_reported():
    """The fix must not turn the check off — a guessed route stays ungrounded."""
    contract = AutomationGenerationContract.model_validate({
        "contractVersion": "1.0", "testCaseId": "TC-0085",
        "scriptType": "playwright-typescript", "businessFlow": "Invalid login",
        "pageObjects": [],
        "assertions": [{"type": "url", "target": "page", "expected": "/client/#/dashboard/home"}],
    })

    assert locator_policy.check_url_targets_grounded(
        contract, ["https://rahulshettyacademy.com/client/#/auth/login"]
    ) == ["url_assertion:/client/#/dashboard/home"]
