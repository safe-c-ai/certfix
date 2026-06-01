"""Rule-card helpers for Top-K CERT-C rule selection experiments."""

# ruff: noqa: E501

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuleCard:
    """Compact discriminator text for one CERT-C rule."""

    rule_id: str
    category: str
    title: str
    cue: str
    applies_when: str
    does_not_apply_when: str
    common_confusions: tuple[str, ...]


@dataclass(frozen=True)
class RuleSelectionVote:
    """One selector run over one candidate permutation."""

    selected_rule: str | None
    ranked_rules: tuple[str, ...]
    parse_ok: bool
    raw: str = ""


@dataclass(frozen=True)
class AggregatedRuleSelection:
    """Aggregated selector result across repeated candidate-order permutations."""

    selected_by_majority: str | None
    selected_by_borda: str | None
    vote_counts: dict[str, int]
    borda_scores: dict[str, int]
    consensus_rate: float
    fallback_used: bool = False


CURATED_RULE_NOTES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "ARR30-C": (
        "An array subscript or pointer value is outside the bounds of the array object.",
        "The issue is pointer arithmetic on a scalar object, invalid pointer comparison, or only an incorrect byte count to a library call.",
        ("ARR32-C", "ARR36-C", "ARR37-C", "ARR38-C", "ARR39-C"),
    ),
    "ARR32-C": (
        "A variable length array or dynamic stack array is created with a nonpositive or otherwise invalid bound.",
        "The issue is ordinary heap allocation size, a fixed-size array index, or pointer arithmetic.",
        ("ARR30-C", "MEM35-C", "INT30-C"),
    ),
    "ARR36-C": (
        "The code subtracts or compares pointers that do not point into the same array object.",
        "The issue is adding an integer to a scalar pointer, an out-of-bounds subscript, or comparing pointer values only to NULL.",
        ("ARR30-C", "ARR37-C", "ARR39-C"),
    ),
    "ARR37-C": (
        "The code adds or subtracts an integer to a pointer to a non-array object such as a scalar or struct object.",
        "The pointer is known to point into an actual array, or the issue is subtracting two unrelated pointers.",
        ("ARR30-C", "ARR36-C", "ARR39-C"),
    ),
    "ARR38-C": (
        "A library function such as memcpy, memmove, memset, or string handling is given a size that forms invalid pointers past the object.",
        "The issue is direct array indexing or arithmetic not involving a library function size/count argument.",
        ("ARR30-C", "ARR39-C", "STR31-C", "MEM35-C"),
    ),
    "ARR39-C": (
        "Pointer arithmetic incorrectly adds a scaled integer, for example adding sizeof(T) units to a T pointer.",
        "The issue is a simple out-of-bounds index, unrelated pointer comparison, or pointer arithmetic on a scalar object.",
        ("ARR30-C", "ARR36-C", "ARR37-C", "ARR38-C"),
    ),
    "DCL30-C": (
        "A pointer or reference can outlive the storage duration of the object it designates.",
        "The issue is use after free of heap memory, reserved identifiers, or uninitialized data.",
        ("MEM30-C", "DCL37-C", "EXP33-C"),
    ),
    "DCL37-C": (
        "The code declares or defines an identifier reserved for the implementation, such as leading underscore forms.",
        "The issue is a storage lifetime bug, conflicting declarations, or a macro misuse without reserved names.",
        ("DCL30-C", "DCL36-C", "PRE30-C"),
    ),
    "EXP30-C": (
        "The result depends on unspecified evaluation order of side effects, such as modifying and reading the same scalar in one expression.",
        "The side effect is inside sizeof, an assignment in an if condition, or merely an argument type mismatch.",
        ("EXP37-C", "EXP44-C", "EXP45-C"),
    ),
    "EXP33-C": (
        "An object with an indeterminate value is read before it is initialized.",
        "The issue is a null pointer dereference, wrong function argument type, or use after free.",
        ("EXP34-C", "EXP37-C", "MEM30-C"),
    ),
    "EXP34-C": (
        "The code dereferences or indexes through a pointer that may be NULL on that path.",
        "The issue is an uninitialized non-pointer value, use after free, or an unchecked allocation size without a dereference.",
        ("EXP33-C", "ERR33-C", "MEM30-C", "MEM35-C"),
    ),
    "EXP35-C": (
        "The code modifies an object with temporary lifetime, such as a compound literal or temporary aggregate that should not be modified.",
        "The issue is returning or storing a pointer that outlives an object, dereferencing NULL, or using a freed object.",
        ("DCL30-C", "MEM30-C", "EXP34-C"),
    ),
    "EXP37-C": (
        "A function is called with an incompatible argument type, count, or function pointer type.",
        "The issue is printf format/argument mismatch, uninitialized data, or evaluation-order side effects.",
        ("EXP30-C", "EXP33-C", "FIO47-C", "STR38-C"),
    ),
    "EXP40-C": (
        "The code attempts to modify a const-qualified object or storage that should be treated as constant.",
        "The issue is modifying a string literal, casting between incompatible pointer types, or pointer/integer conversion.",
        ("STR30-C", "EXP36-C", "EXP39-C", "INT36-C"),
    ),
    "EXP44-C": (
        "The code relies on side effects in operands to sizeof, _Alignof, or _Generic where the side effect is not evaluated.",
        "The issue is ordinary unspecified evaluation order or assignment in a selection statement.",
        ("EXP30-C", "EXP45-C"),
    ),
    "INT30-C": (
        "An unsigned integer operation can wrap around and the wrapped result is used in a security-relevant size, bound, or allocation.",
        "The issue is signed overflow, divide-by-zero, shift-count range, or value truncation during conversion.",
        ("INT31-C", "INT32-C", "INT33-C", "INT34-C", "MEM35-C"),
    ),
    "INT31-C": (
        "An integer conversion can lose, reinterpret, or change the value in a way that affects behavior or bounds.",
        "The issue is arithmetic wrap before conversion, signed overflow, divide by zero, or pointer/integer conversion.",
        ("INT30-C", "INT32-C", "INT33-C", "INT36-C"),
    ),
    "INT32-C": (
        "A signed integer arithmetic operation can overflow or otherwise exceed the representable range.",
        "The issue is unsigned wraparound, narrowing conversion, divide-by-zero, or invalid shift count.",
        ("INT30-C", "INT31-C", "INT33-C", "INT34-C"),
    ),
    "INT33-C": (
        "A division or remainder operation can use zero as the divisor.",
        "The issue is overflow, truncation, invalid shift count, or unchecked allocation.",
        ("INT30-C", "INT32-C", "INT34-C"),
    ),
    "INT34-C": (
        "A shift expression uses a negative shift count or a count greater than or equal to the operand width.",
        "The issue is arithmetic overflow, truncation, divide-by-zero, or Boolean bitwise use.",
        ("INT30-C", "INT32-C", "INT33-C", "EXP46-C"),
    ),
    "INT36-C": (
        "The code converts a pointer to an integer or an integer to a pointer in a way that is not portable or loses information.",
        "The issue is modifying a const object, incompatible pointer aliasing, signed overflow, or unsigned wraparound.",
        ("EXP40-C", "EXP39-C", "INT31-C", "INT32-C"),
    ),
    "STR30-C": (
        "The code attempts to modify a string literal or storage that points to a string literal.",
        "The issue is modifying a const object that is not specifically a string literal, buffer overflow, or missing null termination.",
        ("EXP40-C", "STR31-C", "STR32-C"),
    ),
    "MEM30-C": (
        "A pointer is used after the pointed-to object's lifetime ended, commonly after free(), realloc(), or returning a pointer to expired storage.",
        "The issue is only a memory leak, freeing a nonheap pointer, or allocating too few bytes without a later lifetime-ended use.",
        ("MEM31-C", "MEM34-C", "MEM35-C", "DCL30-C"),
    ),
    "MEM31-C": (
        "Allocated memory is not released on one or more paths before it becomes unreachable or the program exits its required cleanup scope.",
        "The issue is a later use after free, freeing a nonheap pointer, or allocating too few bytes.",
        ("MEM30-C", "MEM34-C", "MEM35-C"),
    ),
    "MEM33-C": (
        "A structure with a flexible array member is copied or allocated as if it were a fixed-size structure, losing the flexible payload.",
        "The issue is a general underallocation, leak, use after free, or nonheap free without a flexible array member.",
        ("MEM31-C", "MEM34-C", "MEM35-C"),
    ),
    "MEM34-C": (
        "The code passes a pointer not returned by a memory allocation function to free() or realloc().",
        "The issue is using a pointer after it has been freed, a leak, or an allocation size that is too small.",
        ("MEM30-C", "MEM31-C", "MEM35-C"),
    ),
    "MEM35-C": (
        "The allocated object is too small for the intended type, element count, or string data that will be stored.",
        "The issue is a leak, use after free, freeing a nonheap pointer, or an array index unrelated to allocation size.",
        ("MEM30-C", "MEM31-C", "MEM34-C", "ARR38-C", "STR31-C"),
    ),
    "ERR33-C": (
        "A standard library or API call can fail and its return value is ignored before the result is used.",
        "The issue is directly dereferencing NULL, wrong arguments, or failing to set errno.",
        ("EXP34-C", "EXP37-C", "ERR30-C"),
    ),
    "STR31-C": (
        "A character array or destination buffer may be too small for the copied string plus the terminating null character.",
        "The issue is missing null termination after bounded copy, signed char conversion, or a generic memory allocation size bug.",
        ("STR32-C", "STR34-C", "ARR38-C", "MEM35-C"),
    ),
    "STR32-C": (
        "A string operation may leave a character sequence without a terminating null character before string use.",
        "The issue is destination buffer capacity for the full string, signed char conversion, or out-of-bounds indexing.",
        ("STR31-C", "STR34-C", "ARR30-C"),
    ),
    "STR34-C": (
        "A plain char value that may be negative is converted to a larger integer type for character classification or EOF-sensitive logic.",
        "The issue is buffer capacity, null termination, or general integer truncation.",
        ("STR31-C", "STR32-C", "INT31-C"),
    ),
    "FIO47-C": (
        "A printf/scanf-style format string does not match the number or types of the supplied arguments.",
        "The issue is a general function prototype mismatch or string buffer overflow.",
        ("EXP37-C", "STR31-C"),
    ),
    "FIO30-C": (
        "Externally controlled input is used directly as a format string for printf, scanf, syslog, or similar functions.",
        "The issue is a fixed format string with wrong arguments, missing null termination, or generic string overflow.",
        ("FIO47-C", "STR31-C", "STR32-C", "EXP37-C"),
    ),
    "FIO37-C": (
        "The code assumes fgets() or fgetws() returned a nonempty string and reads characters such as buf[0] without checking emptiness.",
        "The issue is using a buffer after fgets failure, missing fclose, or missing flush between stream input and output.",
        ("FIO40-C", "FIO42-C", "FIO39-C", "ARR30-C"),
    ),
    "FIO39-C": (
        "The code alternates input and output operations on an update stream without an intervening fflush(), fseek(), fsetpos(), or rewind().",
        "The issue is failing to close a file, using a stale buffer after fgets failure, or ignoring a return value.",
        ("FIO37-C", "FIO40-C", "FIO42-C", "ERR33-C"),
    ),
    "FIO40-C": (
        "The code uses a string buffer after fgets() or fgetws() fails without resetting it to a known string.",
        "The issue is assuming a successful fgets returned nonempty text, missing fclose, or stream input/output sequencing.",
        ("FIO37-C", "FIO39-C", "FIO42-C", "STR32-C"),
    ),
    "FIO42-C": (
        "A file opened with fopen or similar is not closed on all relevant paths after it is no longer needed.",
        "The issue is update-stream sequencing, stale errno, format string misuse, or buffer content after fgets failure.",
        ("FIO39-C", "ERR30-C", "ERR32-C", "FIO40-C"),
    ),
    "ENV33-C": (
        "The code invokes system() or otherwise executes a command processor with externally influenced command text.",
        "The issue is an environment variable read, temporary file race, or POSIX API misuse without command execution.",
        ("ENV31-C", "FIO45-C", "POS30-C"),
    ),
    "SIG30-C": (
        "A signal handler calls a function or performs an operation that is not asynchronous-signal-safe.",
        "The issue is sharing data with a signal handler, raising SIGTERM, or POSIX thread synchronization.",
        ("SIG31-C", "SIG34-C", "CON31-C"),
    ),
    "MSC37-C": (
        "A non-void function can reach the end without returning a value.",
        "The issue is ignored return value, uninitialized read, or a cleanup leak.",
        ("ERR33-C", "EXP33-C", "MEM31-C"),
    ),
    "MSC30-C": (
        "The code uses rand() for security-relevant or otherwise unsuitable pseudorandom number generation.",
        "The issue is failing to seed a PRNG, a library race, or a concurrency problem unrelated to rand().",
        ("MSC32-C", "CON33-C"),
    ),
    "MSC32-C": (
        "The code uses a pseudorandom number generator without proper seeding or with a predictable seed.",
        "The issue is the inherent unsuitability of rand() for security or a thread-safety race in a library function.",
        ("MSC30-C", "CON33-C"),
    ),
    "CON33-C": (
        "The code uses a library function with shared internal state in a way that can race across threads.",
        "The issue is condition-variable liveness, multiple mutexes for a condvar, signal-handler safety, or PRNG seeding.",
        ("CON38-C", "POS53-C", "SIG30-C", "MSC30-C", "MSC32-C"),
    ),
    "CON38-C": (
        "The code uses condition variables in a way that can lose wakeups, violate mutex discipline, or break thread liveness.",
        "The issue is using more than one mutex for one condition variable, a library race, or a POSIX-specific cond_wait rule.",
        ("POS53-C", "CON33-C", "CON35-C", "POS51-C"),
    ),
}


PAIR_GUIDANCE: dict[tuple[str, str], str] = {
    ("ARR30-C", "ARR37-C"): "Choose ARR30-C for out-of-bounds use of an array element or pointer. Choose ARR37-C for arithmetic on a pointer to a scalar or non-array object.",
    ("ARR36-C", "ARR37-C"): "Choose ARR36-C for subtracting or comparing two unrelated pointers. Choose ARR37-C for adding/subtracting an integer to a pointer to a non-array object.",
    ("ARR38-C", "STR31-C"): "Choose ARR38-C when a library count forms invalid object pointers. Choose STR31-C when the key defect is insufficient character storage for a string plus null terminator.",
    ("EXP30-C", "EXP44-C"): "Choose EXP30-C for unspecified ordering between evaluated side effects. Choose EXP44-C when the side effect sits in sizeof, _Alignof, or _Generic and is not evaluated.",
    ("EXP33-C", "EXP34-C"): "Choose EXP33-C for reading an uninitialized object. Choose EXP34-C for dereferencing a pointer that may be NULL.",
    ("EXP34-C", "ERR33-C"): "Choose EXP34-C when a NULL pointer is dereferenced. Choose ERR33-C when an error return is ignored even if no dereference is visible in the snippet.",
    ("EXP35-C", "DCL30-C"): "Prefer EXP35-C when the code accesses an object after its lifetime ended. Use DCL30-C for declarations with storage duration that is wrong before the later access pattern.",
    ("EXP35-C", "MEM30-C"): "Choose EXP35-C for modification of temporary-lifetime storage. Choose MEM30-C only for concrete access after free/realloc/lifetime end.",
    ("EXP37-C", "FIO47-C"): "Choose FIO47-C for printf/scanf format-string argument mismatches. Choose EXP37-C for general function call or function pointer argument mismatches.",
    ("EXP40-C", "STR30-C"): "Choose STR30-C when the constant storage is specifically a string literal. Choose EXP40-C for other const-qualified objects.",
    ("EXP40-C", "INT36-C"): "Choose EXP40-C for modifying a const object. Choose INT36-C for pointer/integer conversion.",
    ("FIO30-C", "FIO47-C"): "Choose FIO30-C for user-controlled format strings. Choose FIO47-C for fixed format strings with wrong argument types or counts.",
    ("FIO37-C", "FIO40-C"): "Choose FIO37-C for assuming a successful fgets result is nonempty. Choose FIO40-C for using the old buffer contents after fgets failure.",
    ("FIO39-C", "FIO42-C"): "Choose FIO39-C for missing flush/positioning between input and output on an update stream. Choose FIO42-C for missing fclose.",
    ("INT30-C", "INT32-C"): "Choose INT30-C for unsigned wraparound. Choose INT32-C for signed overflow.",
    ("INT30-C", "MEM35-C"): "Choose INT30-C if arithmetic wrap creates the bad size. Choose MEM35-C if the allocation expression directly underallocates for the intended object.",
    ("INT31-C", "INT32-C"): "Choose INT31-C for lossy or value-changing conversion. Choose INT32-C for signed arithmetic overflow before conversion.",
    ("MEM33-C", "MEM35-C"): "Choose MEM33-C for flexible array member allocation/copy shape. Choose MEM35-C for general underallocation.",
    ("MEM30-C", "MEM31-C"): "Choose MEM30-C only when there is concrete use after lifetime end. Choose MEM31-C when allocated memory is merely leaked or not freed.",
    ("MEM30-C", "MEM34-C"): "Choose MEM30-C for use after free/realloc/lifetime end. Choose MEM34-C for freeing or reallocating a pointer that was not heap-allocated.",
    ("MEM31-C", "MEM35-C"): "Choose MEM31-C for missing deallocation. Choose MEM35-C for allocating too few bytes or elements.",
    ("MSC30-C", "MSC32-C"): "Choose MSC30-C for using rand() where rand itself is unsuitable. Choose MSC32-C for missing or predictable seeding.",
    ("CON30-C", "MEM31-C"): "Prefer CON30-C when dynamically allocated data is stored in thread-specific storage or TLS and the missing cleanup is tied to thread/task exit, missing destructor, or replacement of a TLS value. Prefer MEM31-C for ordinary dynamically allocated memory that is not stored as thread-specific storage.",
    ("CON33-C", "MSC30-C"): "Choose CON33-C for thread races in library functions. Choose MSC30-C for unsuitable pseudorandom generation.",
    ("CON38-C", "POS53-C"): "Choose POS53-C for using more than one mutex with one condition variable. Choose CON38-C for broader condition-variable liveness or lost-wakeup logic.",
    ("SIG30-C", "SIG35-C"): "Prefer SIG35-C when the shown issue is returning from, or otherwise resuming execution after, a computational exception handler. Use SIG30-C for unsafe calls in a handler when that return/resume signal is absent. Use SIG31-C when the primary evidence is shared-object access in a handler.",
    ("SIG31-C", "SIG35-C"): "Prefer SIG35-C when the shown issue is returning from, or otherwise resuming execution after, a computational exception handler. Use SIG30-C for unsafe calls in a handler when that return/resume signal is absent. Use SIG31-C when the primary evidence is shared-object access in a handler.",
    ("STR31-C", "STR32-C"): "Choose STR31-C for insufficient destination capacity. Choose STR32-C for missing null termination after a bounded operation.",
}


def load_rule_cards(catalog_path: Path | None = None) -> dict[str, RuleCard]:
    """Load CERT-C rule cards from the bundled catalog plus curated discriminators."""

    if catalog_path is None:
        data_ref = resources.files("certfix.data").joinpath("cert_c_rules_with_examples.json")
        data = json.loads(data_ref.read_text(encoding="utf-8"))
    else:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))

    cards: dict[str, RuleCard] = {}
    for category in data["categories"]:
        category_name = str(category["name"])
        for rule in category["rules"]:
            rule_id = str(rule["id"])
            title = str(rule["title"])
            cue = str(rule.get("example") or "")
            applies, does_not_apply, confusions = CURATED_RULE_NOTES.get(
                rule_id,
                (
                    f"The code has concrete evidence for: {title}.",
                    "Another candidate has more specific evidence for the actual operation or failure mode.",
                    (),
                ),
            )
            cards[rule_id] = RuleCard(
                rule_id=rule_id,
                category=category_name,
                title=title,
                cue=cue,
                applies_when=applies,
                does_not_apply_when=does_not_apply,
                common_confusions=confusions,
            )
    return cards


def format_candidate_cards(rule_ids: list[str], cards: dict[str, RuleCard]) -> str:
    """Format candidate cards for a selector prompt."""

    blocks: list[str] = []
    for idx, rule_id in enumerate(rule_ids, 1):
        card = cards[rule_id]
        confusion_text = ", ".join(card.common_confusions) if card.common_confusions else "none listed"
        cue = f"\n  Compact cue: {card.cue}" if card.cue else ""
        blocks.append(
            f"{idx}. {card.rule_id}: {card.title}\n"
            f"  Category: {card.category}{cue}\n"
            f"  Applies when: {card.applies_when}\n"
            f"  Does not apply when: {card.does_not_apply_when}\n"
            f"  Common confusions: {confusion_text}"
        )
    return "\n\n".join(blocks)


def format_pair_guidance(rule_ids: list[str]) -> str:
    """Return contrastive guidance for candidate pairs that have curated notes."""

    blocks: list[str] = []
    seen: set[tuple[str, str]] = set()
    for left in rule_ids:
        for right in rule_ids:
            if left == right:
                continue
            first, second = sorted((left, right))
            key: tuple[str, str] = (first, second)
            if key in seen:
                continue
            seen.add(key)
            guidance = PAIR_GUIDANCE.get(key)
            if guidance:
                blocks.append(f"- {key[0]} vs {key[1]}: {guidance}")
    return "\n".join(blocks) if blocks else "- No curated pair guidance for this set."


def build_rule_selector_prompt(
    code: str,
    candidate_rule_ids: list[str],
    cards: dict[str, RuleCard],
) -> str:
    """Build the Qwen3.6 rule-card selector prompt."""

    candidate_cards = format_candidate_cards(candidate_rule_ids, cards)
    pair_guidance = format_pair_guidance(candidate_rule_ids)
    candidates_json = json.dumps(candidate_rule_ids, ensure_ascii=False)
    return f"""/no_think
You are selecting the single best CERT-C rule from a candidate list.
Every candidate below is plausible. Your task is to discriminate between them
using concrete evidence in the C code, not candidate order.

Candidate rule cards:
{candidate_cards}

Contrastive guidance for this candidate set:
{pair_guidance}

C code:
```c
{code}
```

Return only one JSON object with this exact shape:
{{
  "selected_rule": "MEM30-C",
  "ranked_rules": ["MEM30-C", "MEM31-C"],
  "evidence": "short concrete evidence"
}}

Rules:
- "selected_rule" must be exactly one of: {candidates_json}
- "ranked_rules" must list the same candidate rule IDs from best to worst.
- Prefer direct code evidence over title similarity.
- If two rules look similar, use the contrastive guidance to choose the more specific rule.
- Do not output markdown or explanations outside JSON.
"""


def aggregate_rule_selection(
    votes: list[RuleSelectionVote],
    original_rank: dict[str, int],
    fallback_to_rank1_on_no_valid_vote: bool = False,
) -> AggregatedRuleSelection:
    """Aggregate selector outputs with majority and Borda scoring."""

    vote_counts: dict[str, int] = {}
    borda_scores: dict[str, int] = {}
    candidate_count = len(original_rank)
    valid_vote_count = 0

    for vote in votes:
        if vote.selected_rule in original_rank:
            valid_vote_count += 1
            vote_counts[vote.selected_rule] = vote_counts.get(vote.selected_rule, 0) + 1
        for rank, rule_id in enumerate(vote.ranked_rules, 1):
            if rule_id not in original_rank:
                continue
            borda_scores[rule_id] = borda_scores.get(rule_id, 0) + max(
                candidate_count - rank + 1,
                1,
            )

    selected_by_majority = _best_rule(vote_counts, original_rank)
    selected_by_borda = _best_rule(borda_scores, original_rank)
    fallback_used = False
    if fallback_to_rank1_on_no_valid_vote and not selected_by_majority and original_rank:
        selected_by_majority = min(original_rank, key=original_rank.__getitem__)
        if not selected_by_borda:
            selected_by_borda = selected_by_majority
        fallback_used = True
    max_votes = max(vote_counts.values(), default=0)
    consensus_rate = max_votes / valid_vote_count if valid_vote_count else 0.0
    return AggregatedRuleSelection(
        selected_by_majority=selected_by_majority,
        selected_by_borda=selected_by_borda,
        vote_counts=dict(sorted(vote_counts.items())),
        borda_scores=dict(sorted(borda_scores.items())),
        consensus_rate=consensus_rate,
        fallback_used=fallback_used,
    )


def parse_selector_json(
    raw: str,
    candidate_rule_ids: list[str],
) -> RuleSelectionVote:
    """Parse selector JSON and keep only supplied candidate rules."""

    valid = set(candidate_rule_ids)
    text = _strip_thinking_and_fences(raw)
    data: dict[str, Any] | None = None
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            data = loaded
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                loaded = json.loads(text[start : end + 1])
                if isinstance(loaded, dict):
                    data = loaded
            except json.JSONDecodeError:
                data = None

    if data is None:
        return RuleSelectionVote(selected_rule=None, ranked_rules=(), parse_ok=False, raw=raw)

    selected = str(data.get("selected_rule") or "").strip().upper()
    selected_rule = selected if selected in valid else None
    ranked_rules = _extract_ranked_rules(data, valid)
    if selected_rule and selected_rule not in ranked_rules:
        ranked_rules = (selected_rule, *ranked_rules)
    return RuleSelectionVote(
        selected_rule=selected_rule,
        ranked_rules=ranked_rules,
        parse_ok=bool(selected_rule or ranked_rules),
        raw=raw,
    )


def _extract_ranked_rules(data: dict[str, Any], valid: set[str]) -> tuple[str, ...]:
    ranked = data.get("ranked_rules")
    values: list[Any]
    if isinstance(ranked, list):
        values = ranked
    elif isinstance(ranked, str):
        values = [ranked]
    else:
        values = []

    rules: list[str] = []
    for value in values:
        rule_id = str(value).strip().upper()
        if rule_id in valid and rule_id not in rules:
            rules.append(rule_id)
    return tuple(rules)


def _best_rule(scores: dict[str, int], original_rank: dict[str, int]) -> str | None:
    if not scores:
        return None
    return min(
        scores,
        key=lambda rule_id: (-scores[rule_id], original_rank.get(rule_id, 10_000), rule_id),
    )


def _strip_thinking_and_fences(raw: str) -> str:
    text = raw
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>", start)
        text = text[:start] + text[end + len("</think>") :]
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
