from app.semantic.v2.native_detection_pipeline import NativeDetectionPipeline
from app.semantic.v2.feature_extraction import FeatureExtractionPipeline
from app.semantic.detectors.base import DetectorInput
from app.semantic.detectors.regex_detector import RegexSemanticDetector
from app.semantic.detectors.dictionary_detector import DictionarySemanticDetector
from app.semantic.detectors.value_sampling_detector import ValueSamplingDetector


def test_pipeline_parity_multi_column():
    # create multiple columns
    col1_vals = ("1", "2", "3")
    col2_vals = (" test@example.com ", "user@domain.org")
    c1 = FeatureExtractionPipeline.extract("c1", col1_vals)
    c2 = FeatureExtractionPipeline.extract("c2", col2_vals)
    from app.semantic.v2.semantic_context import SemanticContext
    ctx = SemanticContext(columns=(c1, c2))

    # v1 detectors per column
    v1_results = []
    for col_vals, name in ((col1_vals, "c1"), (col2_vals, "c2")):
        col_res = []
        for det in (RegexSemanticDetector(), DictionarySemanticDetector(), ValueSamplingDetector()):
            r = det.detect(DetectorInput(column_name=name, values=tuple(col_vals)))
            if r and r.classifications:
                col_res.append(r)
        v1_results.append(col_res)

    pipeline = NativeDetectionPipeline()
    v2_results = pipeline.run(ctx)
    assert v1_results == v2_results


def test_pipeline_parity_fused():
    col1_vals = ("1", "2", "3")
    col2_vals = (" test@example.com ", "user@domain.org")
    c1 = FeatureExtractionPipeline.extract("c1", col1_vals)
    c2 = FeatureExtractionPipeline.extract("c2", col2_vals)
    from app.semantic.v2.semantic_context import SemanticContext
    ctx = SemanticContext(columns=(c1, c2))

    v1_results = []
    for col_vals, name in ((col1_vals, "c1"), (col2_vals, "c2")):
        col_res = []
        for det in (RegexSemanticDetector(), DictionarySemanticDetector(), ValueSamplingDetector()):
            r = det.detect(DetectorInput(column_name=name, values=tuple(col_vals)))
            if r and r.classifications:
                col_res.append(r)
        v1_results.append(col_res)

    pipeline = NativeDetectionPipeline()
    fused_results = pipeline.run(ctx, fused=True)
    assert v1_results == fused_results


def test_native_column_evaluator_direct_evaluate_parity():
    col_vals = ("1", "2", "3")
    c = FeatureExtractionPipeline.extract("c", col_vals)
    from app.semantic.v2.native_detectors import NativeColumnEvaluator

    evaluator = NativeColumnEvaluator()
    results = evaluator.evaluate(c)

    expected = []
    for det in (RegexSemanticDetector(), DictionarySemanticDetector(), ValueSamplingDetector()):
        r = det.detect(DetectorInput(column_name="c", values=tuple(col_vals)))
        if r and r.classifications:
            expected.append(r)

    assert list(results) == expected
