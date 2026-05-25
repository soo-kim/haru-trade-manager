from app.core.logging_coverage import PRD_13_3_COVERAGE, missing_points, required_point_count


def test_logging_coverage_matrix_has_required_points():
    assert len(PRD_13_3_COVERAGE) == required_point_count()
    assert missing_points() == []


def test_logging_coverage_status_values_are_allowed():
    allowed = {"planned", "partial", "implemented"}
    for item in PRD_13_3_COVERAGE.values():
        assert item.status in allowed
        assert item.prd_point
        assert item.evidence
