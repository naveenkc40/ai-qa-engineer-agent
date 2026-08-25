from app import read_multiline_requirement


def input_from(lines):
    values = iter(lines)
    return lambda: next(values)


def test_read_multiline_requirement_stops_at_end():
    requirement = read_multiline_requirement(
        input_from(["first line", "second line", "END", "ignored"])
    )

    assert requirement == "first line\nsecond line"


def test_read_multiline_requirement_accepts_lowercase_end():
    requirement = read_multiline_requirement(input_from(["requirement", "end"]))

    assert requirement == "requirement"


def test_read_multiline_requirement_accepts_whitespace_around_end():
    requirement = read_multiline_requirement(input_from(["requirement", "  END  "]))

    assert requirement == "requirement"


def test_read_multiline_requirement_allows_empty_input_before_end():
    requirement = read_multiline_requirement(input_from(["END"]))

    assert requirement == ""
