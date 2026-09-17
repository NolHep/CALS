from cals.classify import (
    TOPICS,
    TOPICS_BY_KEY,
    class_action_confidence,
    nature_of_suit_code,
    topics_for,
)


def test_obvious_class_action_scores_high(recap_payload):
    case = recap_payload["results"][1]
    score, reasons = class_action_confidence(case)
    assert score >= 0.9
    assert any("class action" in r for r in reasons)


def test_unrelated_criminal_case_scores_zero(recap_payload):
    case = recap_payload["results"][2]
    score, reasons = class_action_confidence(case)
    assert score == 0.0
    assert reasons == []


def test_score_is_capped_at_one():
    case = {
        "caseName": "class action",
        "cause": "class action complaint similarly situated putative class",
        "suitNature": "890 Other Statutory Actions",
        "recap_documents": [
            {"snippet": "rule 23 class certification on behalf of all others"}
        ],
    }
    score, _ = class_action_confidence(case)
    assert score == 1.0


def test_nature_of_suit_code_extraction():
    assert nature_of_suit_code({"suitNature": "890 Other Statutory Actions"}) == "890"
    assert nature_of_suit_code({"suitNature": None}) is None
    assert nature_of_suit_code({"suitNature": "Other"}) is None


def test_topics_detected_from_text(recap_payload):
    topics = topics_for(recap_payload["results"][1])
    assert "data_privacy" in topics


def test_topics_fall_back_to_distinctive_nature_of_suit():
    assert "securities" in topics_for({"suitNature": "850 Securities"})
    assert "antitrust" in topics_for({"suitNature": "410 Antitrust"})
    assert "employment" in topics_for({"suitNature": "710 Fair Labor Standards"})


def test_generic_nature_of_suit_does_not_tag_topics():
    """890 and 370 are shared by many topics; tagging from them is noise."""
    assert topics_for({"suitNature": "890 Other Statutory Actions"}) == []
    assert topics_for({"suitNature": "370 Other Fraud"}) == []
    assert topics_for({"suitNature": "380 Personal Property: Other"}) == []


def test_a_data_breach_case_is_not_tagged_as_a_product_case():
    case = {
        "suitNature": "380 Personal Property: Other",
        "recap_documents": [{"snippet": "exposed in the data breach"}],
    }
    assert topics_for(case) == ["data_privacy"]


def test_unrelated_case_has_no_topics(recap_payload):
    assert topics_for(recap_payload["results"][2]) == []


def test_topic_keys_are_unique_and_indexed():
    assert len(TOPICS_BY_KEY) == len(TOPICS)
    for topic in TOPICS:
        assert topic.label and topic.query_terms


def test_criminal_docket_is_flagged_unlikely():
    from cals.classify import is_unlikely_class_action

    assert is_unlikely_class_action({"docketNumber": "3:26-cr-00123"})
    assert not is_unlikely_class_action({"docketNumber": "3:26-cv-10046"})


def test_habeas_and_immigration_are_flagged_unlikely():
    from cals.classify import is_unlikely_class_action

    assert is_unlikely_class_action({"suitNature": "530 Habeas Corpus: General"})
    assert is_unlikely_class_action({"suitNature": "463 Alien Detainee"})
    assert not is_unlikely_class_action({"suitNature": "890 Other Statutory"})


def test_ordinary_civil_docket_is_not_flagged():
    from cals.classify import is_unlikely_class_action

    assert not is_unlikely_class_action({})
