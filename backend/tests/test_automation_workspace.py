from app.services.automation_runner.workspace import google_locale_cookie


def test_google_locale_cookie_matches_non_com_tlds():
    # The whole point of this fix: google.ae (and other non-.com TLDs)
    # render Arabic/localized UI by default, breaking locators grounded
    # against an English-rendered page, unless PREF=hl=en is sent for the
    # domain actually being tested — not a hardcoded .google.com.
    cookie = google_locale_cookie("https://www.google.ae/index.html")
    assert cookie["domain"] == ".google.ae"
    assert cookie["name"] == "PREF"
    assert cookie["value"] == "hl=en"


def test_google_locale_cookie_matches_dot_com():
    cookie = google_locale_cookie("https://www.google.com/search")
    assert cookie["domain"] == ".google.com"


def test_google_locale_cookie_matches_multi_label_tld():
    cookie = google_locale_cookie("https://www.google.co.uk/")
    assert cookie["domain"] == ".google.co.uk"


def test_google_locale_cookie_matches_subdomain():
    cookie = google_locale_cookie("https://accounts.google.com/signin")
    assert cookie["domain"] == ".google.com"


def test_google_locale_cookie_none_for_non_google_domain():
    assert google_locale_cookie("https://example.com/app") is None


def test_google_locale_cookie_does_not_false_match_lookalike_domain():
    # "notgoogle.com" must not match — "google" has to be a whole label.
    assert google_locale_cookie("https://notgoogle.com/") is None
    assert google_locale_cookie("https://googlesomethingelse.com/") is None


def test_google_locale_cookie_none_for_missing_url():
    assert google_locale_cookie(None) is None
    assert google_locale_cookie("") is None
