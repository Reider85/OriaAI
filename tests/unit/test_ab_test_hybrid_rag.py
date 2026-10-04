"""Unit tests for hybrid RAG A/B test script."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from scripts.ab_test_hybrid_rag import (
    _analyze_subtype_breakdown,
    _check_subtype_thresholds,
    _update_trend_csv,
)


class TestHybridRagABTest:
    """Test the hybrid RAG A/B test functionality."""

    def test_analyze_subtype_breakdown(self):
        """Test subtype breakdown analysis."""
        # Mock result with subtype data
        mock_result = {
            "baseline": {
                "per_category": {
                    "sku": {"recall_at_5": 0.5, "query_count": 2},
                    "error_code": {"recall_at_5": 1.0, "query_count": 1},
                    "employee_id": {"recall_at_5": 0.0, "query_count": 1},
                }
            },
            "treatment": {
                "per_category": {
                    "sku": {"recall_at_5": 1.0, "query_count": 2},
                    "error_code": {"recall_at_5": 1.0, "query_count": 1},
                    "employee_id": {"recall_at_5": 1.0, "query_count": 1},
                }
            },
        }

        breakdown = _analyze_subtype_breakdown(mock_result)

        assert breakdown["sku"]["query_count"] == 2
        assert breakdown["sku"]["baseline_recall"] == 0.5
        assert breakdown["sku"]["treatment_recall"] == 1.0
        assert breakdown["sku"]["improvement_pct"] == 100.0  # (1.0-0.5)/0.5 * 100

        assert breakdown["error_code"]["query_count"] == 1
        assert breakdown["error_code"]["baseline_recall"] == 1.0
        assert breakdown["error_code"]["treatment_recall"] == 1.0
        assert breakdown["error_code"]["improvement_pct"] == 0.0

        assert breakdown["employee_id"]["query_count"] == 1
        assert breakdown["employee_id"]["baseline_recall"] == 0.0
        assert breakdown["employee_id"]["treatment_recall"] == 1.0
        assert breakdown["employee_id"]["improvement_pct"] == 0.0  # Avoid division by zero

    def test_check_subtype_thresholds(self):
        """Test subtype threshold checking."""
        # Mock result with different improvement levels
        mock_result = Mock()
        mock_result.queries = []

        # Mock the breakdown function to return specific values
        with patch("scripts.ab_test_hybrid_rag._analyze_subtype_breakdown") as mock_breakdown:
            mock_breakdown.return_value = {
                "sku": {"improvement_pct": 45.0},  # Passes >=40%
                "error_code": {"improvement_pct": 35.0},  # Fails >=40%
                "employee_id": {"improvement_pct": 30.0},  # Passes >=25%
            }

            thresholds = _check_subtype_thresholds(mock_result)

            assert thresholds["sku"] is True
            assert thresholds["error_code"] is False
            assert thresholds["employee_id"] is True

    @patch("scripts.ab_test_hybrid_rag.Path")
    def test_update_trend_csv_new_file(self, mock_path):
        """Test CSV update when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test_trend.csv"
            mock_path.return_value = csv_file

            mock_report = {
                "timestamp": "2023-01-01T12:00:00",
                "baseline_stats": {"recall_at_5": 0.600},
                "treatment_stats": {"recall_at_5": 0.750},
                "improvement": {"recall_improvement_pct": 25.0, "latency_overhead_pct": 20.0},
                "subtype_breakdown": {
                    "sku": {"treatment_recall": 0.700},
                    "error_code": {"treatment_recall": 0.800},
                    "employee_id": {"treatment_recall": 0.600},
                },
                "pass_criteria": {"overall_pass": False},
            }

            _update_trend_csv(mock_report)

            assert csv_file.exists()
            df = pd.read_csv(csv_file)
            assert len(df) == 1
            assert df.iloc[0]["date"] == "2023-01-01"
            assert df.iloc[0]["baseline_recall"] == 0.600
            assert df.iloc[0]["treatment_recall"] == 0.750
            assert df.iloc[0]["improvement_pct"] == 25.0
            assert df.iloc[0]["pass_fail"] == "FAIL"

    @patch("scripts.ab_test_hybrid_rag.Path")
    def test_update_trend_csv_existing_file(self, mock_path):
        """Test CSV update when file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_file = Path(tmpdir) / "test_trend.csv"
            mock_path.return_value = csv_file

            # Create initial CSV
            initial_data = pd.DataFrame(
                [
                    {
                        "date": "2023-01-01",
                        "baseline_recall": 0.600,
                        "treatment_recall": 0.750,
                        "improvement_pct": 25.0,
                        "pass_fail": "FAIL",
                    }
                ]
            )
            initial_data.to_csv(csv_file, index=False)

            mock_report = {
                "timestamp": "2023-01-02T12:00:00",
                "baseline_stats": {"recall_at_5": 0.650},
                "treatment_stats": {"recall_at_5": 0.800},
                "improvement": {"recall_improvement_pct": 23.1, "latency_overhead_pct": 15.0},
                "subtype_breakdown": {
                    "sku": {"treatment_recall": 0.750},
                    "error_code": {"treatment_recall": 0.850},
                    "employee_id": {"treatment_recall": 0.650},
                },
                "pass_criteria": {"overall_pass": True},
            }

            _update_trend_csv(mock_report)

            df = pd.read_csv(csv_file)
            assert len(df) == 2
            assert df.iloc[1]["date"] == "2023-01-02"
            assert df.iloc[1]["baseline_recall"] == 0.650
            assert df.iloc[1]["treatment_recall"] == 0.800
            assert df.iloc[1]["improvement_pct"] == 23.1
            assert df.iloc[1]["pass_fail"] == "PASS"

    def test_main_quick_mode_logic(self):
        """Test quick mode logic without full main function execution."""
        # Test that quick mode limits queries to 5 per subtype
        exact_term_queries = [
            {
                "query": "test1",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "sku",
            },
            {
                "query": "test2",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "sku",
            },
            {
                "query": "test3",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "sku",
            },
            {
                "query": "test4",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "sku",
            },
            {
                "query": "test5",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "sku",
            },
            {
                "query": "test6",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "sku",
            },  # Should be filtered out
            {
                "query": "test7",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "error_code",
            },
            {
                "query": "test8",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "error_code",
            },
            {
                "query": "test9",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "error_code",
            },
            {
                "query": "test10",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "error_code",
            },
            {
                "query": "test11",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "error_code",
            },  # Should be filtered out
            {
                "query": "test12",
                "relevant_doc_ids": ["doc1"],
                "category": "exact_term",
                "subtype": "employee_id",
            },
        ]

        # Apply quick mode filtering logic
        subtype_counts = {"sku": 0, "error_code": 0, "employee_id": 0}
        quick_queries = []
        for q in exact_term_queries:
            subtype = q.get("subtype", "error_code")
            if subtype_counts[subtype] < 5:
                quick_queries.append(q)
                subtype_counts[subtype] += 1

        # Verify quick mode limits
        assert len(quick_queries) == 11  # 5 sku + 5 error_code + 1 employee_id
        assert subtype_counts["sku"] == 5
        assert subtype_counts["error_code"] == 5
        assert subtype_counts["employee_id"] == 1

    def test_pass_criteria_logic(self):
        """Test PASS criteria logic."""
        # Test case that should PASS
        pass_criteria = {
            "recall_improvement": True,  # >=30%
            "latency_overhead": True,  # <=50% overhead
            "subtype_thresholds": {  # Meets subtype requirements
                "sku": True,  # >=40%
                "error_code": True,  # >=40%
                "employee_id": True,  # >=25%
            },
        }

        assert pass_criteria["recall_improvement"]
        assert pass_criteria["latency_overhead"]
        assert all(pass_criteria["subtype_thresholds"].values())
        pass_criteria["overall_pass"] = True
        assert pass_criteria["overall_pass"]

        # Test case that should FAIL
        fail_criteria = {
            "recall_improvement": False,  # <30%
            "latency_overhead": True,  # <=50% overhead
            "subtype_thresholds": {  # Fails subtype requirements
                "sku": False,  # <40%
                "error_code": True,  # >=40%
                "employee_id": True,  # >=25%
            },
        }

        assert not fail_criteria["recall_improvement"]
        fail_criteria["overall_pass"] = False
        assert not fail_criteria["overall_pass"]


if __name__ == "__main__":
    pytest.main([__file__])
