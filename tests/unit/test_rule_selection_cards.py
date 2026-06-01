from certfix.core.rule_selection_cards import (
    RuleSelectionVote,
    aggregate_rule_selection,
    format_candidate_cards,
    format_pair_guidance,
    load_rule_cards,
    parse_selector_json,
)


def test_load_rule_cards_adds_curated_mem30_discriminator() -> None:
    cards = load_rule_cards()

    card = cards["MEM30-C"]

    assert card.title
    assert "used after" in card.applies_when.lower()
    assert "MEM31-C" in card.common_confusions


def test_format_candidate_cards_includes_does_not_apply() -> None:
    cards = load_rule_cards()

    text = format_candidate_cards(["MEM30-C", "MEM31-C"], cards)

    assert "MEM30-C" in text
    assert "Does not apply when" in text
    assert "Common confusions" in text


def test_format_pair_guidance_includes_curated_pair() -> None:
    text = format_pair_guidance(["MEM31-C", "MEM30-C", "EXP34-C"])

    assert "MEM30-C vs MEM31-C" in text
    assert "use after" in text.lower()


def test_parse_selector_json_accepts_fenced_json_and_filters_candidates() -> None:
    raw = """```json
{
  "selected_rule": "MEM30-C",
  "ranked_rules": ["MEM30-C", "NOT-A-RULE", "MEM31-C"],
  "evidence": "p is used after free"
}
```"""

    vote = parse_selector_json(raw, ["MEM30-C", "MEM31-C"])

    assert vote.parse_ok is True
    assert vote.selected_rule == "MEM30-C"
    assert vote.ranked_rules == ("MEM30-C", "MEM31-C")


def test_parse_selector_json_rejects_outside_selected_rule() -> None:
    vote = parse_selector_json(
        '{"selected_rule":"EXP34-C","ranked_rules":["MEM31-C"]}',
        ["MEM30-C", "MEM31-C"],
    )

    assert vote.selected_rule is None
    assert vote.ranked_rules == ("MEM31-C",)
    assert vote.parse_ok is True


def test_aggregate_rule_selection_uses_majority_and_borda_tie_breaks() -> None:
    votes = [
        RuleSelectionVote("MEM31-C", ("MEM31-C", "MEM30-C", "EXP34-C"), True),
        RuleSelectionVote("MEM30-C", ("MEM30-C", "MEM31-C", "EXP34-C"), True),
        RuleSelectionVote("MEM30-C", ("MEM31-C", "MEM30-C", "EXP34-C"), True),
    ]
    original_rank = {"MEM30-C": 1, "MEM31-C": 2, "EXP34-C": 3}

    result = aggregate_rule_selection(votes, original_rank)

    assert result.selected_by_majority == "MEM30-C"
    assert result.selected_by_borda == "MEM31-C"
    assert result.vote_counts == {"MEM30-C": 2, "MEM31-C": 1}
    assert result.consensus_rate == 2 / 3


def test_aggregate_rule_selection_ties_by_original_rank() -> None:
    votes = [
        RuleSelectionVote("MEM31-C", ("MEM31-C", "MEM30-C"), True),
        RuleSelectionVote("MEM30-C", ("MEM30-C", "MEM31-C"), True),
    ]
    original_rank = {"MEM30-C": 1, "MEM31-C": 2}

    result = aggregate_rule_selection(votes, original_rank)

    assert result.selected_by_majority == "MEM30-C"
    assert result.selected_by_borda == "MEM30-C"


def test_aggregate_rule_selection_falls_back_to_rank1_when_all_votes_invalid() -> None:
    votes = [
        RuleSelectionVote(None, (), False),
        RuleSelectionVote(None, ("UNKNOWN-C",), False),
    ]
    original_rank = {"FIO37-C": 1, "FIO39-C": 2}

    result = aggregate_rule_selection(
        votes,
        original_rank,
        fallback_to_rank1_on_no_valid_vote=True,
    )

    assert result.selected_by_majority == "FIO37-C"
    assert result.selected_by_borda == "FIO37-C"
    assert result.fallback_used is True
    assert result.consensus_rate == 0.0
