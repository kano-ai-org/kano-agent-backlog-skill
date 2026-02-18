"""Accuracy validation system for tokenizer adapters.

This module provides tools to validate tokenizer accuracy against real model
tokenizers, measure accuracy percentages, and identify systematic biases.

Features:
- Compare token counts with actual model tokenizers
- Accuracy percentage measurement and reporting
- Systematic bias detection and analysis
- Regression test generation
- Performance impact assessment
"""

import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class AccuracyTestCase:
    """Test case for accuracy validation."""
    
    text: str
    expected_tokens: int
    model_name: str
    source: str  # "manual", "tiktoken", "huggingface", etc.
    language: Optional[str] = None
    text_type: Optional[str] = None  # "code", "prose", "technical", etc.
    
    def __post_init__(self):
        """Validate test case data."""
        if not self.text:
            raise ValueError("Text cannot be empty")
        if self.expected_tokens < 0:
            raise ValueError("Expected tokens must be non-negative")
        if not self.model_name:
            raise ValueError("Model name cannot be empty")


@dataclass
class AccuracyResult:
    """Result of accuracy validation for a single test case."""
    
    test_case: AccuracyTestCase
    predicted_tokens: int
    adapter_id: str
    tokenizer_id: str
    is_exact: bool
    absolute_error: int = field(init=False)
    relative_error: float = field(init=False)
    processing_time_ms: float = 0.0
    
    def __post_init__(self):
        """Calculate error metrics."""
        self.absolute_error = abs(self.predicted_tokens - self.test_case.expected_tokens)
        
        if self.test_case.expected_tokens > 0:
            self.relative_error = self.absolute_error / self.test_case.expected_tokens
        else:
            self.relative_error = 0.0 if self.absolute_error == 0 else float('inf')


@dataclass
class AccuracyReport:
    """Comprehensive accuracy report for a tokenizer adapter."""
    
    adapter_id: str
    model_name: str
    test_cases_count: int
    results: List[AccuracyResult]
    
    # Aggregate metrics
    mean_absolute_error: float = field(init=False)
    mean_relative_error: float = field(init=False)
    median_absolute_error: float = field(init=False)
    median_relative_error: float = field(init=False)
    max_absolute_error: int = field(init=False)
    max_relative_error: float = field(init=False)
    accuracy_within_1_token: float = field(init=False)
    accuracy_within_5_percent: float = field(init=False)
    accuracy_within_10_percent: float = field(init=False)
    
    # Performance metrics
    mean_processing_time_ms: float = field(init=False)
    total_processing_time_ms: float = field(init=False)
    
    def __post_init__(self):
        """Calculate aggregate metrics."""
        if not self.results:
            # Initialize all metrics to 0 for empty results
            self.mean_absolute_error = 0.0
            self.mean_relative_error = 0.0
            self.median_absolute_error = 0.0
            self.median_relative_error = 0.0
            self.max_absolute_error = 0
            self.max_relative_error = 0.0
            self.accuracy_within_1_token = 0.0
            self.accuracy_within_5_percent = 0.0
            self.accuracy_within_10_percent = 0.0
            self.mean_processing_time_ms = 0.0
            self.total_processing_time_ms = 0.0
            return
        
        # Error metrics
        absolute_errors = [r.absolute_error for r in self.results]
        relative_errors = [r.relative_error for r in self.results if r.relative_error != float('inf')]
        
        self.mean_absolute_error = statistics.mean(absolute_errors)
        self.median_absolute_error = statistics.median(absolute_errors)
        self.max_absolute_error = max(absolute_errors)
        
        if relative_errors:
            self.mean_relative_error = statistics.mean(relative_errors)
            self.median_relative_error = statistics.median(relative_errors)
            self.max_relative_error = max(relative_errors)
        else:
            self.mean_relative_error = 0.0
            self.median_relative_error = 0.0
            self.max_relative_error = 0.0
        
        # Accuracy thresholds
        within_1_token = sum(1 for r in self.results if r.absolute_error <= 1)
        within_5_percent = sum(1 for r in self.results if r.relative_error <= 0.05)
        within_10_percent = sum(1 for r in self.results if r.relative_error <= 0.10)
        
        self.accuracy_within_1_token = within_1_token / len(self.results)
        self.accuracy_within_5_percent = within_5_percent / len(self.results)
        self.accuracy_within_10_percent = within_10_percent / len(self.results)
        
        # Performance metrics
        processing_times = [r.processing_time_ms for r in self.results]
        self.mean_processing_time_ms = statistics.mean(processing_times)
        self.total_processing_time_ms = sum(processing_times)
    
    def get_accuracy_grade(self) -> str:
        """Get overall accuracy grade based on metrics."""
        if self.accuracy_within_5_percent >= 0.95:
            return "A+"  # Excellent: 95%+ within 5%
        elif self.accuracy_within_5_percent >= 0.90:
            return "A"   # Very Good: 90%+ within 5%
        elif self.accuracy_within_10_percent >= 0.90:
            return "B+"  # Good: 90%+ within 10%
        elif self.accuracy_within_10_percent >= 0.80:
            return "B"   # Acceptable: 80%+ within 10%
        elif self.accuracy_within_10_percent >= 0.70:
            return "C"   # Fair: 70%+ within 10%
        else:
            return "D"   # Poor: <70% within 10%


class AccuracyValidator:
    """Validator for tokenizer adapter accuracy."""
    
    def __init__(self):
        """Initialize accuracy validator."""
        self.test_cases: List[AccuracyTestCase] = []
        self._load_default_test_cases()
    
    def _load_default_test_cases(self) -> None:
        """Load default test cases for common scenarios."""
        # Basic English text
        self.test_cases.extend([
            AccuracyTestCase(
                text="Hello, world!",
                expected_tokens=4,  # Based on tiktoken cl100k_base
                model_name="gpt-3.5-turbo",
                source="manual",
                language="en",
                text_type="simple"
            ),
            AccuracyTestCase(
                text="The quick brown fox jumps over the lazy dog.",
                expected_tokens=10,
                model_name="gpt-3.5-turbo",
                source="manual",
                language="en",
                text_type="prose"
            ),
            AccuracyTestCase(
                text="This is a longer sentence that contains multiple clauses and should be tokenized into several tokens to test the accuracy of different tokenizer implementations.",
                expected_tokens=28,
                model_name="gpt-3.5-turbo",
                source="manual",
                language="en",
                text_type="prose"
            ),
        ])
        
        # Technical/code text
        self.test_cases.extend([
            AccuracyTestCase(
                text="def hello_world():\n    print('Hello, world!')",
                expected_tokens=12,
                model_name="gpt-3.5-turbo",
                source="manual",
                language="en",
                text_type="code"
            ),
            AccuracyTestCase(
                text="import numpy as np\nfrom sklearn.model_selection import train_test_split",
                expected_tokens=14,
                model_name="gpt-3.5-turbo",
                source="manual",
                language="en",
                text_type="code"
            ),
        ])
        
        # Special characters and punctuation
        self.test_cases.extend([
            AccuracyTestCase(
                text="Hello! How are you? I'm fine, thanks. What about you?",
                expected_tokens=16,
                model_name="gpt-3.5-turbo",
                source="manual",
                language="en",
                text_type="conversational"
            ),
            AccuracyTestCase(
                text="Email: user@example.com, Phone: +1-555-123-4567",
                expected_tokens=13,
                model_name="gpt-3.5-turbo",
                source="manual",
                language="en",
                text_type="structured"
            ),
        ])
        
        # Numbers and mixed content
        self.test_cases.extend([
            AccuracyTestCase(
                text="The temperature is 23.5°C (74.3°F) today.",
                expected_tokens=13,
                model_name="gpt-3.5-turbo",
                source="manual",
                language="en",
                text_type="mixed"
            ),
            AccuracyTestCase(
                text="Price: $1,234.56 (including 8.25% tax)",
                expected_tokens=11,
                model_name="gpt-3.5-turbo",
                source="manual",
                language="en",
                text_type="financial"
            ),
        ])
    
    def add_test_case(self, test_case: AccuracyTestCase) -> None:
        """Add a custom test case."""
        self.test_cases.append(test_case)
    
    def add_test_cases_from_file(self, file_path: Path) -> int:
        """Load test cases from JSON file.
        
        Args:
            file_path: Path to JSON file containing test cases
            
        Returns:
            Number of test cases loaded
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            loaded_count = 0
            for case_data in data.get('test_cases', []):
                try:
                    test_case = AccuracyTestCase(**case_data)
                    self.test_cases.append(test_case)
                    loaded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to load test case: {e}")
            
            logger.info(f"Loaded {loaded_count} test cases from {file_path}")
            return loaded_count
            
        except Exception as e:
            logger.error(f"Failed to load test cases from {file_path}: {e}")
            return 0
    
    def validate_adapter(self, adapter, model_name: Optional[str] = None) -> AccuracyReport:
        """Validate accuracy of a tokenizer adapter.
        
        Args:
            adapter: TokenizerAdapter instance to validate
            model_name: Optional model name filter
            
        Returns:
            AccuracyReport with validation results
        """
        # Filter test cases by model if specified
        test_cases = self.test_cases
        if model_name:
            test_cases = [tc for tc in test_cases if tc.model_name == model_name]
        
        if not test_cases:
            logger.warning(f"No test cases found for model: {model_name}")
            return AccuracyReport(
                adapter_id=adapter.adapter_id,
                model_name=model_name or "unknown",
                test_cases_count=0,
                results=[]
            )
        
        results = []
        
        for test_case in test_cases:
            try:
                # Measure processing time
                start_time = time.perf_counter()
                token_count = adapter.count_tokens(test_case.text)
                end_time = time.perf_counter()
                
                processing_time_ms = (end_time - start_time) * 1000
                
                result = AccuracyResult(
                    test_case=test_case,
                    predicted_tokens=token_count.count,
                    adapter_id=adapter.adapter_id,
                    tokenizer_id=token_count.tokenizer_id,
                    is_exact=token_count.is_exact,
                    processing_time_ms=processing_time_ms
                )
                
                results.append(result)
                
            except Exception as e:
                logger.error(f"Failed to validate test case '{test_case.text[:50]}...': {e}")
                # Create error result
                error_result = AccuracyResult(
                    test_case=test_case,
                    predicted_tokens=-1,  # Indicate error
                    adapter_id=adapter.adapter_id,
                    tokenizer_id="error",
                    is_exact=False,
                    processing_time_ms=0.0
                )
                results.append(error_result)
        
        return AccuracyReport(
            adapter_id=adapter.adapter_id,
            model_name=model_name or adapter.model_name,
            test_cases_count=len(test_cases),
            results=results
        )
    
    def compare_adapters(self, adapters: List[Any], model_name: Optional[str] = None) -> Dict[str, AccuracyReport]:
        """Compare accuracy of multiple adapters.
        
        Args:
            adapters: List of TokenizerAdapter instances
            model_name: Optional model name filter
            
        Returns:
            Dictionary mapping adapter IDs to their accuracy reports
        """
        reports = {}
        
        for adapter in adapters:
            try:
                report = self.validate_adapter(adapter, model_name)
                reports[adapter.adapter_id] = report
            except Exception as e:
                logger.error(f"Failed to validate adapter {adapter.adapter_id}: {e}")
        
        return reports
    
    def generate_accuracy_summary(self, reports: Dict[str, AccuracyReport]) -> str:
        """Generate a human-readable accuracy summary.
        
        Args:
            reports: Dictionary of accuracy reports
            
        Returns:
            Formatted summary string
        """
        if not reports:
            return "No accuracy reports available."
        
        lines = ["# Tokenizer Accuracy Validation Report", ""]
        
        # Overall summary
        lines.append("## Summary")
        lines.append("")
        
        for adapter_id, report in reports.items():
            grade = report.get_accuracy_grade()
            lines.append(f"**{adapter_id}**: Grade {grade}")
            lines.append(f"- Test cases: {report.test_cases_count}")
            lines.append(f"- Within 5%: {report.accuracy_within_5_percent:.1%}")
            lines.append(f"- Within 10%: {report.accuracy_within_10_percent:.1%}")
            lines.append(f"- Mean absolute error: {report.mean_absolute_error:.2f} tokens")
            lines.append(f"- Mean relative error: {report.mean_relative_error:.1%}")
            lines.append("")
        
        # Detailed results
        lines.append("## Detailed Results")
        lines.append("")
        
        for adapter_id, report in reports.items():
            lines.append(f"### {adapter_id}")
            lines.append("")
            lines.append("| Text | Expected | Predicted | Error | Rel Error |")
            lines.append("|------|----------|-----------|-------|-----------|")
            
            for result in report.results[:10]:  # Show first 10 results
                text_preview = result.test_case.text[:30] + "..." if len(result.test_case.text) > 30 else result.test_case.text
                rel_error_str = f"{result.relative_error:.1%}" if result.relative_error != float('inf') else "∞"
                
                lines.append(f"| {text_preview} | {result.test_case.expected_tokens} | {result.predicted_tokens} | {result.absolute_error} | {rel_error_str} |")
            
            if len(report.results) > 10:
                lines.append(f"| ... ({len(report.results) - 10} more results) | | | | |")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def save_report(self, reports: Dict[str, AccuracyReport], output_path: Path) -> None:
        """Save accuracy reports to JSON file.
        
        Args:
            reports: Dictionary of accuracy reports
            output_path: Path to save the report
        """
        try:
            # Convert reports to serializable format
            serializable_reports = {}
            
            for adapter_id, report in reports.items():
                serializable_reports[adapter_id] = {
                    "adapter_id": report.adapter_id,
                    "model_name": report.model_name,
                    "test_cases_count": report.test_cases_count,
                    "mean_absolute_error": report.mean_absolute_error,
                    "mean_relative_error": report.mean_relative_error,
                    "median_absolute_error": report.median_absolute_error,
                    "median_relative_error": report.median_relative_error,
                    "max_absolute_error": report.max_absolute_error,
                    "max_relative_error": report.max_relative_error,
                    "accuracy_within_1_token": report.accuracy_within_1_token,
                    "accuracy_within_5_percent": report.accuracy_within_5_percent,
                    "accuracy_within_10_percent": report.accuracy_within_10_percent,
                    "mean_processing_time_ms": report.mean_processing_time_ms,
                    "total_processing_time_ms": report.total_processing_time_ms,
                    "accuracy_grade": report.get_accuracy_grade(),
                    "results": [
                        {
                            "text": result.test_case.text,
                            "expected_tokens": result.test_case.expected_tokens,
                            "predicted_tokens": result.predicted_tokens,
                            "absolute_error": result.absolute_error,
                            "relative_error": result.relative_error,
                            "processing_time_ms": result.processing_time_ms,
                            "text_type": result.test_case.text_type,
                            "language": result.test_case.language
                        }
                        for result in report.results
                    ]
                }
            
            # Save to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(serializable_reports, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved accuracy report to {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to save accuracy report: {e}")
            raise


def create_default_validator() -> AccuracyValidator:
    """Create a default accuracy validator with standard test cases."""
    return AccuracyValidator()