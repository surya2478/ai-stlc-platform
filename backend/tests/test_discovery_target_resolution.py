"""Why a step that names a real control can still resolve to nothing.

Written from a live failure (discovery session 33, project 13). The step
"Click the Register button and capture the HTTP response" ran against
`https://rahulshettyacademy.com/client/#/auth/register` with the form fully
rendered, and captured no element at all. The model built from that session had
one screen, zero elements and zero gaps, published clean, and grounded nothing.

Two things were wrong. The page carries two controls with the exact accessible
name "Register" — a hero link and the submit button — and resolution read the
label the step gave while discarding the role it gave in the same breath, so a
question the step had already answered was refused. And when a refusal *is*
right, it left no trace anyone could act on.
"""
from types import SimpleNamespace

from app.agents.automation.snapshot_parser import parse_snapshot
from app.services.discovery.step_interpreter import (
    interpret_step,
    resolve_target_ref,
    screen_ref_for,
)

# Trimmed from the accessibility snapshot actually stored on action 74, keeping
# both elements named "Register" — the hero link and the submit button.
REGISTER_PAGE = """### Page
- Page URL: https://rahulshettyacademy.com/client/#/auth/register
- Page Title: Let's Shop
### Snapshot
```yaml
- generic [ref=e22]:
  - generic [ref=e23]:
    - heading "Practice Website for Rahul Shetty Academy Students" [level=1] [ref=e24]
    - link "Register" [ref=e26] [cursor=pointer]
  - generic [ref=e29]:
    - heading "Register" [level=1] [ref=e30]
    - textbox "First Name" [ref=e36]
    - textbox "Last Name" [ref=e40]
    - button "Register" [ref=e69] [cursor=pointer]
```
"""

SINGLE_REGISTER_PAGE = """### Page
- Page URL: https://rahulshettyacademy.com/client/#/auth/register
- Page Title: Let's Shop
### Snapshot
```yaml
- generic [ref=e29]:
  - textbox "First Name" [ref=e36]
  - button "Register" [ref=e69] [cursor=pointer]
```
"""

# The same collision with no role to separate the two: whichever control the
# step meant, "button" cannot say which.
TWO_REGISTER_BUTTONS = """### Page
- Page URL: https://rahulshettyacademy.com/client/#/auth/register
### Snapshot
```yaml
- generic [ref=e29]:
  - button "Register" [ref=e68] [cursor=pointer]
  - button "Register" [ref=e69] [cursor=pointer]
```
"""


def test_the_named_role_separates_two_controls_sharing_a_label():
    parsed = parse_snapshot(REGISTER_PAGE)
    interpreted = interpret_step("Click the Register button and capture the HTTP response")

    assert interpreted.action_family == "click"
    assert interpreted.target_label == "Register"
    assert interpreted.target_role == "button"
    # A link and a button both answer to "Register", and the step says which.
    # Reading that is not a guess — it is in the step's own words.
    assert resolve_target_ref(parsed, interpreted) == "e69"


def test_naming_the_link_selects_the_link():
    """The hint follows the step rather than preferring any particular role."""
    parsed = parse_snapshot(REGISTER_PAGE)

    assert resolve_target_ref(parsed, interpret_step("Click the Register link")) == "e26"


def test_a_collision_the_wording_cannot_break_still_resolves_to_nothing():
    parsed = parse_snapshot(TWO_REGISTER_BUTTONS)
    interpreted = interpret_step("Click the Register button and capture the HTTP response")

    assert resolve_target_ref(parsed, interpreted) is None


def test_a_misnamed_role_does_not_narrow_an_unambiguous_match():
    """Steps call things "buttons" that are marked up as links all the time.

    Narrowing only ever breaks a tie, so calling the sole `button "Register"` a
    link still resolves to it rather than refusing.
    """
    parsed = parse_snapshot(SINGLE_REGISTER_PAGE)

    assert resolve_target_ref(parsed, interpret_step("Click the Register link")) == "e69"


def test_the_same_step_resolves_once_the_page_is_unambiguous():
    """Pins that the refusal is about the page, not about the step's wording."""
    parsed = parse_snapshot(SINGLE_REGISTER_PAGE)
    interpreted = interpret_step("Click the Register button and capture the HTTP response")

    assert resolve_target_ref(parsed, interpreted) == "e69"


def test_a_fill_step_naming_no_value_is_not_treated_as_an_interaction():
    """The other half of why session 33 captured nothing.

    "Fill in valid values for all fields except userEmail" names neither a
    field nor a value, so there is nothing to type and nothing to type it into.
    Recording it as an observation is right; the point of pinning it is that
    input capture requires an explicit value, which most written steps omit.
    """
    interpreted = interpret_step("Fill in valid values for all fields except userEmail, leaving it blank")

    assert interpreted.action_family == "read"
    assert interpreted.needs_target is False


# --- Fields whose accessible name is their placeholder ----------------------
#
# An input with no label takes its name from its placeholder, and placeholders
# are routinely example values. TC-0102 is entirely about the register page's
# email field, whose name is `email@example.com` — characters the target
# pattern used to reject, so no wording of the step could name it.

EMAIL_FIELD_PAGE = """### Page
- Page URL: https://rahulshettyacademy.com/client/#/auth/register
### Snapshot
```yaml
- generic [ref=e41]:
  - textbox "First Name" [ref=e36]
  - textbox "email@example.com" [ref=e44]
```
"""


def test_a_field_named_by_an_example_email_can_be_targeted():
    parsed = parse_snapshot(EMAIL_FIELD_PAGE)
    interpreted = interpret_step("Enter 'invalidemail.com' in the 'email@example.com' field")

    assert interpreted.action_family == "input"
    assert interpreted.input_text == "invalidemail.com"
    assert resolve_target_ref(parsed, interpreted) == "e44"


def test_an_ordinary_field_name_is_unaffected():
    interpreted = interpret_step("Enter 'John' in the First Name field")

    assert interpreted.action_family == "input"
    assert interpreted.target_label == "First Name"


def test_a_trailing_full_stop_does_not_become_part_of_the_label():
    """Guards the cost of admitting `.` into labels.

    Absorbing the sentence's own punctuation would capture "First Name field."
    and promote a step that reads as an observation into an input that can
    never resolve — a MISSING_ELEMENT gap on every step ending in a full stop.
    """
    interpreted = interpret_step("Enter 'John' in the First Name field.")

    assert interpreted.action_family == "read"


# --- "the X input field" vs "the X input" -----------------------------------
#
# The root cause behind sessions #34 and #35 (project 14, same page, same
# control, opposite outcomes). A written step names the KIND of control it
# means; an accessible name almost never contains that word. Whether a step
# resolved came down to how many of those nouns the author happened to type,
# which no author could have known and no reviewer could have spotted.

GREENKART = """### Page
- Page URL: https://rahulshettyacademy.com/seleniumPractise/#/
### Snapshot
```yaml
- generic [ref=e1]:
  - searchbox "Search for Vegetables and Fruits" [ref=e10]
  - button "Search" [ref=e11]
```
"""


def test_control_nouns_do_not_decide_whether_a_step_resolves():
    parsed = parse_snapshot(GREENKART)
    wordings = [
        "Type 'ApPLe' into the Search input",         # session #34 — resolved
        "Type 'cucu' into the Search input field",    # session #35 — refused
        "Enter 'apple' in the Search box",
        "Enter 'apple' in the Search textbox",
    ]

    refs = [resolve_target_ref(parsed, interpret_step(w)) for w in wordings]

    assert refs == ["e10"] * 4


def test_the_written_label_still_wins_when_it_is_the_real_name():
    """Stripping is only ever a second attempt, so a control actually named
    with a control noun is still matched on its real name.

    Written as a quoted step on purpose. An UNQUOTED input step never reaches
    the resolver with its noun intact — `_INPUT_TARGET_RE` consumes one
    trailing noun during extraction, so "in the Search box" arrives as
    "Search" and a control truly named "Search box" cannot be reached that
    way. Quoting the accessible name is the way to say which you mean; that
    limitation predates this variant logic and is left alone deliberately,
    since widening the extraction would change the element slug every step
    produces.
    """
    parsed = parse_snapshot("""### Page
- Page URL: https://x.test/
### Snapshot
```yaml
- generic [ref=e1]:
  - button "Search box" [ref=e20]
  - button "Search" [ref=e21]
```
""")

    assert resolve_target_ref(parsed, interpret_step("Click the 'Search box' button")) == "e20"


def test_stripping_does_not_let_an_input_step_grab_a_button():
    """The role filter still applies to every variant — `button "Search"` is
    not a candidate for a step that types."""
    parsed = parse_snapshot(GREENKART)

    assert resolve_target_ref(parsed, interpret_step("Type 'x' into the Search input field")) == "e10"
    assert resolve_target_ref(parsed, interpret_step("Click the Search button")) == "e11"


def test_a_real_ambiguity_is_not_widened_away():
    """Two controls sharing a name stay a refusal — rewording the needle does
    not make the page less ambiguous."""
    parsed = parse_snapshot("""### Page
- Page URL: https://x.test/
### Snapshot
```yaml
- generic [ref=e1]:
  - textbox "Search" [ref=e30]
  - textbox "Search" [ref=e31]
```
""")

    assert resolve_target_ref(parsed, interpret_step("Type 'x' into the Search field")) is None


# --- Screen identity on a hash-routed app ----------------------------------
#
# `screen_ref_for` used to strip the fragment, so every route in a hash-routed
# SPA produced the same screen reference. Session 33 recorded
# `screen-rahulshettyacademy-com-client` for all four of its actions across the
# register route, and the Application Model — which upserts screen nodes by
# that reference — could never have represented more than one screen for the
# whole application.


def _snapshot_at(url):
    return SimpleNamespace(page_url=url)


def test_two_spa_routes_are_two_screens():
    login = screen_ref_for(_snapshot_at("https://rahulshettyacademy.com/client/#/auth/login"))
    register = screen_ref_for(_snapshot_at("https://rahulshettyacademy.com/client/#/auth/register"))

    assert login != register
    assert login == "screen-rahulshettyacademy-com-client-auth-login"
    assert register == "screen-rahulshettyacademy-com-client-auth-register"


def test_the_shell_url_is_still_its_own_screen():
    assert (
        screen_ref_for(_snapshot_at("https://rahulshettyacademy.com/client/"))
        == "screen-rahulshettyacademy-com-client"
    )


def test_a_bare_anchor_is_the_same_screen_not_a_new_one():
    """`#summary` is a position on the page you are already on, not a route."""
    page = screen_ref_for(_snapshot_at("https://docs.example.com/guide"))
    anchored = screen_ref_for(_snapshot_at("https://docs.example.com/guide#summary"))

    assert page == anchored == "screen-docs-example-com-guide"


def test_query_strings_do_not_split_one_screen_into_many():
    """Query params carry data, so including them would mint a node per visit."""
    a = screen_ref_for(_snapshot_at("https://shop.example.com/checkout?step=2"))
    b = screen_ref_for(_snapshot_at("https://shop.example.com/checkout?step=3"))

    assert a == b == "screen-shop-example-com-checkout"


def test_a_query_inside_the_fragment_is_dropped_for_the_same_reason():
    a = screen_ref_for(_snapshot_at("https://app.example.com/#/search?q=shoes"))
    b = screen_ref_for(_snapshot_at("https://app.example.com/#/search?q=hats"))

    assert a == b == "screen-app-example-com-search"


def test_no_url_means_no_screen_reference():
    assert screen_ref_for(_snapshot_at(None)) is None
