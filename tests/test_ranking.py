from app.services.ranking_service import (
    calculate_match_score,
    extract_model_number,
    extract_storage,
    normalize,
    strict_model_match,
)


# --- normalize -------------------------------------------------------------

def test_normalize_lowercases():
    assert normalize("Hello World") == "hello world"


def test_normalize_strips_special_characters():
    assert normalize("iPhone 15 (128 GB) - Black") == "iphone 15 128 gb black"


def test_normalize_collapses_whitespace():
    assert normalize("  too   many   spaces  ") == "too many spaces"


# --- extract_model_number --------------------------------------------------

def test_extract_model_number_from_iphone():
    assert extract_model_number("iphone 15") == "15"


def test_extract_model_number_from_galaxy():
    assert extract_model_number("galaxy s 24") == "24"


def test_extract_model_number_returns_none_for_no_numbers():
    assert extract_model_number("no numbers") is None


# --- extract_storage -------------------------------------------------------

def test_extract_storage_gb():
    assert extract_storage("128gb") == "128"


def test_extract_model_number_tb_not_matched_by_gb_pattern():
    assert extract_storage("2tb") is None


def test_extract_storage_returns_none_when_absent():
    assert extract_storage("no storage") is None


# --- strict_model_match ----------------------------------------------------

def test_strict_model_match_equal_models_gives_positive():
    score = strict_model_match("iphone 15 128gb", "apple iphone 15 128gb black")
    assert score > 0
    assert score >= 40  # +20 model + +20 storage


def test_strict_model_match_different_models_gives_negative():
    score = strict_model_match("iphone 15", "iphone 14")
    assert score < 0


def test_strict_model_match_missing_model_gives_zero():
    score = strict_model_match("no numbers", "also none")
    assert score == 0


# --- calculate_match_score -------------------------------------------------

def test_identical_titles_score_high():
    score = calculate_match_score("iphone 15 128gb", "iphone 15 128gb")
    assert score >= 90


def test_similar_titles_score_reasonably():
    score = calculate_match_score("iphone 15 128gb black", "apple iphone 15 128gb")
    assert score >= 60


def test_completely_different_titles_score_low():
    score = calculate_match_score("iphone 15", "samsung refrigerator 400l")
    assert score < 50


def test_model_match_adds_bonus():
    base = calculate_match_score("galaxy s24 256gb", "samsung galaxy s24 ultra 256gb")
    no_match = calculate_match_score("galaxy s24 256gb", "samsung galaxy s23 256gb")
    assert base > no_match


def test_storage_match_adds_bonus():
    with_storage = calculate_match_score("iphone 15 256gb", "apple iphone 15 256gb black")
    without_storage = calculate_match_score("iphone 15", "apple iphone 15 black")
    assert with_storage >= without_storage
