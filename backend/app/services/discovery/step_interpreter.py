"""Read a written test step and decide what the browser should actually do.

Guided User Recording walks an approved test case's steps. It used to record
each one as `action_family="read"` and take a snapshot without performing
anything, so a step reading "Click the 'Home' link" produced a screenshot of
whatever page the browser was already on, stored as that step's evidence. The
capture was real; the label was not.

This turns a step's own words into a concrete action the existing
`_execute_action_family` can run, plus the target to run it against.

Three rules hold everything together:

**Never guess an interaction.** A step that cannot be read confidently becomes
`read` — an honest observation — not a click at a plausible-looking element.
Clicking the wrong thing produces evidence that is worse than none, because it
looks deliberate.

**Resolve targets against the snapshot, never against convention.** An element
reference comes from a live accessibility snapshot or it stays empty. An empty
one is a `MISSING_ELEMENT` gap the reviewer can see, which is the honest
outcome; a fabricated one silently grounds tests on an element that was never
observed.

**The step's text is never mutated.** Approved steps are immutable during
execution (UI-015 Section 3.1). This reads them; it does not rewrite them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Ordered: the first pattern that matches wins, so more specific verbs must
# come before more general ones. "navigate to the home page and click Login"
# is a navigate — the step's leading verb is the action it names.
_NAVIGATE_VERBS = ("navigate to", "go to", "open the page", "open page", "browse to", "load the page", "visit")
_CLICK_VERBS = ("click", "select the", "press the", "tap", "choose the", "follow the")
_INPUT_VERBS = ("enter", "type", "fill in", "fill the", "input", "populate")
# Deliberately last and deliberately broad: anything assert-shaped is an
# observation, and so is anything unrecognised.
_READ_VERBS = ("verify", "check", "assert", "confirm", "observe", "validate", "ensure", "see", "review")

# "Click the 'Home' link" / 'Click the "Home" link' / “Home”
_QUOTED_RE = re.compile(r"['\"‘’“”]([^'\"‘’“”]{1,80})['\"‘’“”]")
_URL_RE = re.compile(r"https?://[^\s'\"<>)]+")
# The UI nouns an unquoted label sits in front of: "Click the Home link".
#
# Matched individually rather than as one label-plus-noun pattern because some
# of these words are also labels — "Tap the Menu icon" matched on "menu" and
# left "Tap the" as the label, which strips to nothing. Scanning each noun and
# preferring the rightmost gets "Menu" from that step.
_UI_NOUN_RE = re.compile(r"\b(?:link|button|tab|menu|option|field|box|icon)\b", re.IGNORECASE)
# The nouns that name an ARIA role outright, and so can tell two controls
# sharing an accessible name apart. Only unambiguous ones are mapped: "field",
# "box" and "icon" describe no single role, and "menu" is both a role and a
# common word for the thing that opens one, so they contribute no hint.
_NOUN_ROLES = {"link": "link", "button": "button", "tab": "tab", "option": "option"}
_WORD_RE = re.compile(r"[\w&/'-]+")
# A label longer than this is prose, not the name of a control.
_MAX_LABEL_WORDS = 4

# Words that can only be leading noise on a label, never the start of one.
# Stripped from the front until a real word remains — which also makes "click
# the link" collapse to nothing, correctly refusing to pick a link for the user.
_LEADING_NOISE = frozenset(
    _CLICK_VERBS + _INPUT_VERBS + _READ_VERBS
    + ("the", "a", "an", "this", "that", "each", "any", "on", "in", "into", "and", "then", "please")
    + tuple(v.split()[0] for v in _CLICK_VERBS + _INPUT_VERBS + _READ_VERBS + _NAVIGATE_VERBS)
)
# "Enter 'x' in the Name field" / "Type foo into Email"
#
# `@` and `.` are label characters because a placeholder is an accessible name.
# An unlabelled input takes its name from its placeholder, and placeholders are
# routinely example values — the register page's email field is named
# `email@example.com`, so a step could not name the one field TC-0102 is about.
#
# The label must still *end* on a word character. Without that, allowing `.`
# made "Enter 'x' in the Name field." (a trailing full stop) capture
# "Name field." and turn a step that used to read as an observation into a
# failed input, which is gap noise on every existing step that ends in
# punctuation.
_INPUT_TARGET_RE = re.compile(
    r"\b(?:in|into|for)\s+(?:the\s+)?['\"]?([\w &@./-]{0,39}?\w)['\"]?\s*(?:field|box|input|textbox)?\s*$",
    re.IGNORECASE,
)

# Roles a click may land on. A step saying "click" must not resolve to a
# heading or a paragraph just because the text matched.
_CLICKABLE_ROLES = frozenset({"link", "button", "menuitem", "tab", "option", "checkbox", "radio", "switch"})
_INPUT_ROLES = frozenset({"textbox", "searchbox", "combobox", "spinbutton", "slider"})


@dataclass(frozen=True)
class InterpretedStep:
    """What a step asks for, as far as it can be read from its own words."""

    action_family: str
    # Present only for navigate. Taken from the step text; never synthesised
    # from a base URL, since a guessed destination is unverifiable.
    url: str | None = None
    # The visible label the step named, used to find the element in a snapshot
    # and to describe the action in evidence.
    target_label: str | None = None
    # The ARIA role the step's own wording named ("...the Register *button*"),
    # when it named one. Only ever used to break a tie between elements that
    # share a label — never to narrow an already-unambiguous match, so a step
    # calling a `role=link` control a "button" keeps resolving as it did.
    target_role: str | None = None
    input_text: str | None = None

    @property
    def needs_target(self) -> bool:
        return self.action_family in ("click", "input")


def _first_verb_match(text: str, verbs: tuple[str, ...]) -> bool:
    return any(verb in text for verb in verbs)


def _quoted(text: str) -> str | None:
    match = _QUOTED_RE.search(text)
    return match.group(1).strip() if match else None


def _labelled(text: str) -> str | None:
    """The label sitting before a UI noun, with leading noise removed.

    "Click the Services tab" -> "Services". "Click the link" -> None, because
    once the verb and article are stripped nothing is left naming a control —
    and a click with no named target must not be performed.
    """
    best: str | None = None
    for noun in _UI_NOUN_RE.finditer(text):
        words = _WORD_RE.findall(text[: noun.start()])
        while words and words[0].lower() in _LEADING_NOISE:
            words.pop(0)
        if words:
            # Rightmost wins: a later noun has more of the phrase before it, so
            # its label is the more complete one.
            best = " ".join(words[-_MAX_LABEL_WORDS:])
    return best


def _role_hint(text: str) -> str | None:
    """The role the step named, if it named one.

    Read independently of the label rather than returned alongside it, because
    a quoted label wins over `_labelled` in `interpret_step` — and "Click the
    'Register' button" names its role just as plainly as the unquoted form.

    Rightmost wins, matching `_labelled`'s choice, so the hint always describes
    the same noun phrase the label was taken from.
    """
    hint = None
    for noun in _UI_NOUN_RE.finditer(text):
        role = _NOUN_ROLES.get(noun.group(0).lower())
        if role:
            hint = role
    return hint


def interpret_step(step_text: str) -> InterpretedStep:
    """Classify one step. Unreadable steps become `read`, never a guess."""
    text = (step_text or "").strip()
    if not text:
        return InterpretedStep(action_family="read")
    lowered = text.lower()

    # An explicit URL plus a navigation verb is the only case where a
    # destination is known rather than assumed.
    url_match = _URL_RE.search(text)
    if _first_verb_match(lowered, _NAVIGATE_VERBS):
        if url_match:
            return InterpretedStep(action_family="navigate", url=url_match.group(0).rstrip(".,"))
        # "Navigate to the services page" names no address. Following it would
        # mean inventing one, so this is recorded as an observation instead.
        return InterpretedStep(action_family="read", target_label=_quoted(text) or _labelled(text))

    if _first_verb_match(lowered, _INPUT_VERBS):
        value = _quoted(text)
        target = None
        target_match = _INPUT_TARGET_RE.search(text)
        if target_match:
            target = target_match.group(1).strip()
        return InterpretedStep(
            action_family="input" if (value is not None and target) else "read",
            target_label=target or _labelled(text),
            target_role=_role_hint(text),
            input_text=value,
        )

    if _first_verb_match(lowered, _CLICK_VERBS):
        label = _quoted(text) or _labelled(text)
        # A click with nothing to click is not a click.
        return InterpretedStep(
            action_family="click" if label else "read",
            target_label=label,
            target_role=_role_hint(text),
        )

    if _first_verb_match(lowered, _READ_VERBS):
        return InterpretedStep(action_family="read", target_label=_quoted(text) or _labelled(text))

    return InterpretedStep(action_family="read", target_label=_quoted(text) or _labelled(text))


def _normalize(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "")).strip().casefold()


# The words a step uses to say what KIND of control it means, which are almost
# never part of the control's accessible name. An accessible name comes from a
# label, placeholder or aria-label — "Search for Vegetables and Fruits" — while
# a written step says "the Search input field". Both name the same control.
_TRAILING_CONTROL_NOUN_RE = re.compile(
    r"(?:\s+(?:link|button|tab|menu|option|field|box|input|textbox|dropdown|checkbox|radio|icon))+$",
    re.IGNORECASE,
)


def _label_variants(label: str) -> list[str]:
    """The label as the step wrote it, then the same label with trailing
    control nouns removed.

    This is the difference between a step that works and one that does not,
    for reasons no author could see. Sessions #34 and #35 walked the same
    control on the same page:

        "Type 'ApPLe' into the Search input"        -> "Search"        resolved
        "Type 'cucu' into the Search input field"   -> "Search input"  refused

    The accessible name is "Search for Vegetables and Fruits". "Search"
    substring-matches it; "Search input" does not. One extra word — which
    changes nothing about what a human being would do — silently produced an
    element-less Application Model and, downstream, an ungrounded script.

    The written label is always tried first, so a control genuinely named
    "Search box" still wins on its real name. Stripping only ever adds an
    attempt after the literal one has already failed, and every attempt still
    has to resolve to exactly one element, so this widens what can be found
    without weakening the refusal to guess.
    """
    stripped = _TRAILING_CONTROL_NOUN_RE.sub("", label).strip()
    return [label] if not stripped or stripped == label else [label, stripped]


def resolve_target_ref(parsed_snapshot, interpreted: InterpretedStep) -> str | None:
    """Find the element a step named, in the page as it currently stands.

    Returns None whenever the match is not unambiguous — after reading the role
    the step named, if it named one (see `_single`). That is the important case,
    not a failure mode: the caller records the action without an element
    reference, the model build raises MISSING_ELEMENT, and a human is asked.
    Picking the "closest" candidate would bury that question under a plausible
    answer.
    """
    label = _normalize(interpreted.target_label or "")
    if not label or parsed_snapshot is None:
        return None

    roles = _CLICKABLE_ROLES if interpreted.action_family == "click" else _INPUT_ROLES
    candidates = [
        el for el in getattr(parsed_snapshot, "elements", [])
        if el.ref and el.role in roles and el.name
    ]

    for variant in _label_variants(label):
        exact = [el for el in candidates if _normalize(el.name) == variant]
        resolved = _single(exact, interpreted)
        if resolved is not None:
            return resolved
        if exact:
            # Several elements carry the same accessible name and the step gave
            # nothing to tell them apart — the page is ambiguous here and only a
            # person can say which was meant. A genuine ambiguity is not made
            # less ambiguous by rewording the needle, so stop rather than widen.
            return None
        resolved = _single([el for el in candidates if variant in _normalize(el.name)], interpreted)
        if resolved is not None:
            return resolved
    return None


def _single(matches: list, interpreted: InterpretedStep) -> str | None:
    """The one element these matches point at, or nothing.

    A step that names a role is read for that role before giving up. The
    register page carries a `link "Register"` in its hero and a
    `button "Register"` submitting the form; "Click the Register button" says
    which, and discarding that was reading the step less carefully than it was
    written. This is not the guess the module refuses to make — the
    disambiguator comes from the step's own words, not from proximity, document
    order or a confidence score.

    Applied only after an unqualified match has already failed, so narrowing can
    never turn a resolving step into a refusing one.
    """
    if len(matches) == 1:
        return matches[0].ref
    if len(matches) > 1 and interpreted.target_role:
        by_role = [el for el in matches if el.role == interpreted.target_role]
        if len(by_role) == 1:
            return by_role[0].ref
    return None


def screen_ref_for(parsed_snapshot) -> str | None:
    """A stable screen identifier for the page currently loaded.

    Derived from the observed URL, so it is a fact about where the browser
    actually was, not a name someone chose. This is what the Application Model
    builds screen nodes from — without it a session produces no model at all.

    A routing fragment counts as part of the address. On a hash-routed SPA the
    fragment *is* the route, so dropping it collapsed every screen in the app
    onto one node: discovery session 33 walked
    `https://rahulshettyacademy.com/client/#/auth/register` and recorded the
    same `screen-rahulshettyacademy-com-client` for all four of its actions,
    leaving a model that could never tell one screen from another. Same lesson
    `locator_policy._explored_paths` already learned from the other direction.

    A bare anchor (`#summary`) is not a route — it is a position on the screen
    you are already on — so only `#/…` is treated as address. The query string
    stays excluded either way: it usually carries data (ids, search terms) that
    would split one screen into a new node per visit.
    """
    url = getattr(parsed_snapshot, "page_url", None)
    if not url:
        return None
    without_scheme = re.sub(r"^https?://", "", url.strip())
    path, _, fragment = without_scheme.partition("#")
    path = path.split("?", 1)[0]
    if fragment.startswith("/"):
        # The fragment can carry its own query for the same reason the path can.
        path = f"{path}{fragment.split('?', 1)[0]}"
    # Host included: two apps in one session are two sets of screens.
    slug = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-").lower()
    return f"screen-{slug or 'root'}"[:200]
