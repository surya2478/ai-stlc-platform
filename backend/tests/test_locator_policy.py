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
        "page.getByRole('button', { name: 'Sign in' })"
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


def test_render_locator_pytest_role_uses_snake_case_api():
    assert locator_policy.render_locator_pytest("role", "Sign in", "button") == \
        "page.get_by_role('button', name='Sign in')"
    assert locator_policy.render_locator_pytest("testid", "order-id") == "page.get_by_test_id('order-id')"
