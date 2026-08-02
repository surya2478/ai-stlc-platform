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
_INPUT_TARGET_RE = re.compile(
    r"\b(?:in|into|for)\s+(?:the\s+)?['\"]?([\w &/-]{1,40}?)['\"]?\s*(?:field|box|input|textbox)?\s*$",
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
            input_text=value,
        )

    if _first_verb_match(lowered, _CLICK_VERBS):
        label = _quoted(text) or _labelled(text)
        # A click with nothing to click is not a click.
        return InterpretedStep(
            action_family="click" if label else "read",
            target_label=label,
        )

    if _first_verb_match(lowered, _READ_VERBS):
        return InterpretedStep(action_family="read", target_label=_quoted(text) or _labelled(text))

    return InterpretedStep(action_family="read", target_label=_quoted(text) or _labelled(text))


def _normalize(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "")).strip().casefold()


def resolve_target_ref(parsed_snapshot, interpreted: InterpretedStep) -> str | None:
    """Find the element a step named, in the page as it currently stands.

    Returns None whenever the match is not unambiguous. That is the important
    case, not a failure mode: the caller records the action without an element
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

    exact = [el for el in candidates if _normalize(el.name) == label]
    if len(exact) == 1:
        return exact[0].ref
    if exact:
        # Several elements carry the same accessible name — the page itself is
        # ambiguous here and only a person can say which was meant.
        return None

    contains = [el for el in candidates if label in _normalize(el.name)]
    return contains[0].ref if len(contains) == 1 else None


def screen_ref_for(parsed_snapshot) -> str | None:
    """A stable screen identifier for the page currently loaded.

    Derived from the observed URL path, so it is a fact about where the browser
    actually was, not a name someone chose. This is what the Application Model
    builds screen nodes from — without it a session produces no model at all.
    """
    url = getattr(parsed_snapshot, "page_url", None)
    if not url:
        return None
    without_scheme = re.sub(r"^https?://", "", url.strip())
    path = without_scheme.split("?", 1)[0].split("#", 1)[0]
    # Host included: two apps in one session are two sets of screens.
    slug = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-").lower()
    return f"screen-{slug or 'root'}"[:200]
