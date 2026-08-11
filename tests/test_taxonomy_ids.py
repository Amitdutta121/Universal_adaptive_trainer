from app.curriculum.taxonomy_ids import subtopic_id_from_names, topic_id_from_name


def test_topic_id_is_stable_across_spelling_noise() -> None:
    assert topic_id_from_name("Loops") == topic_id_from_name("  loops ")
    assert topic_id_from_name("Loops").startswith("top-")


def test_subtopic_id_includes_topic_path() -> None:
    a = subtopic_id_from_names("Loops", "While loops")
    b = subtopic_id_from_names("Control flow", "While loops")
    assert a != b
    assert a.startswith("sub-")
