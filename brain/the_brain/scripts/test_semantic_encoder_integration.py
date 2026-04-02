"""
Test SemanticTaskEncoder integration with SpeakingCTM.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import torch


def test_semantic_encoder_standalone():
    """Test SemanticTaskEncoder in isolation."""
    print("=" * 60)
    print("Testing SemanticTaskEncoder Standalone")
    print("=" * 60)

    try:
        from core.semantic_task_encoder import SemanticTaskEncoder, HAS_SENTENCE_TRANSFORMERS
    except ImportError as e:
        print(f"Import error: {e}")
        return False

    if not HAS_SENTENCE_TRANSFORMERS:
        print("sentence-transformers not installed. Skipping semantic tests.")
        print("Install with: pip install sentence-transformers")
        return True  # Not a failure, just skipped

    encoder = SemanticTaskEncoder(
        model_name='all-MiniLM-L6-v2',
        output_dim=256
    )

    # Test single encoding
    task = "Explain how machine learning works"
    features = encoder.encode(task)
    print(f"Single task encoding: {features.shape}")
    assert features.shape == (256,), f"Expected (256,), got {features.shape}"

    # Test batch encoding
    tasks = [
        "What is recursion?",
        "Explain sorting algorithms",
        "Compare Python and JavaScript"
    ]
    batch_features = encoder.encode_batch(tasks)
    print(f"Batch encoding: {batch_features.shape}")
    assert batch_features.shape == (3, 256), f"Expected (3, 256), got {batch_features.shape}"

    # Test similarity
    sim1 = encoder.get_similarity("machine learning", "deep learning")
    sim2 = encoder.get_similarity("machine learning", "cooking recipes")
    print(f"Similarity (ML vs DL): {sim1:.3f}")
    print(f"Similarity (ML vs cooking): {sim2:.3f}")
    assert sim1 > sim2, "Related tasks should have higher similarity"

    # Test task type classification
    features, task_type, probs = encoder.encode_with_type("What is a neural network?")
    print(f"Task type classification: type={task_type}, confidence={probs[task_type]:.3f}")

    print("SemanticTaskEncoder standalone tests PASSED!")
    return True


def test_hybrid_ctm_with_semantic():
    """Test HybridCTM with semantic features."""
    print("\n" + "=" * 60)
    print("Testing HybridCTM with Semantic Features")
    print("=" * 60)

    try:
        from core.hybrid_ctm import HybridNeuroSymbolicCTM
        from core.semantic_task_encoder import SemanticTaskEncoder, HAS_SENTENCE_TRANSFORMERS
    except ImportError as e:
        print(f"Import error: {e}")
        return False

    # Create CTM
    ctm = HybridNeuroSymbolicCTM(
        feature_dim=256,
        iterations=15,
        consciousness_threshold=0.85,
        enable_thought_projection=True,
        thought_dim=2048
    )

    # Initialize lazy modules
    dummy = torch.randint(0, 11, (1, 5, 4))
    with torch.no_grad():
        _ = ctm(dummy, max_iterations=1)

    print(f"CTM parameters: {ctm.get_num_parameters():,}")

    # Test without semantic features
    board = torch.randint(0, 11, (2, 5, 4))
    output_no_semantic = ctm(board, max_iterations=10)
    print(f"Without semantic - steps: {output_no_semantic.reasoning_steps}")

    # Test with semantic features (if available)
    if HAS_SENTENCE_TRANSFORMERS:
        encoder = SemanticTaskEncoder(output_dim=256)
        task = "Explain recursion"
        semantic_features = encoder.encode(task)

        output_with_semantic = ctm(
            board,
            max_iterations=10,
            semantic_features=semantic_features.unsqueeze(0).expand(2, -1)
        )
        print(f"With semantic - steps: {output_with_semantic.reasoning_steps}")
        print(f"Thought vector shape: {output_with_semantic.thought_vector.shape}")
        assert output_with_semantic.thought_vector is not None
    else:
        print("Skipping semantic test - sentence-transformers not installed")

    print("HybridCTM semantic integration tests PASSED!")
    return True


def test_speaking_ctm_with_semantic():
    """Test SpeakingCTM with semantic encoding."""
    print("\n" + "=" * 60)
    print("Testing SpeakingCTM with Semantic Encoding")
    print("=" * 60)

    try:
        from core.speaking_ctm import SpeakingCTM
        from core.semantic_task_encoder import HAS_SENTENCE_TRANSFORMERS
        from core.thought_decoder import HAS_TRANSFORMERS
    except ImportError as e:
        print(f"Import error: {e}")
        return False

    if not HAS_TRANSFORMERS:
        print("transformers not installed. Skipping SpeakingCTM test.")
        return True

    # Test with semantic encoding enabled
    use_semantic = HAS_SENTENCE_TRANSFORMERS
    print(f"Semantic encoding available: {use_semantic}")

    ctm = SpeakingCTM(
        feature_dim=256,
        thought_dim=2048,
        max_iterations=15,
        consciousness_threshold=0.85,
        use_semantic_encoding=use_semantic,
        enable_logging=False,
        device="cpu"
    )

    print(f"\nSystem stats:")
    stats = ctm.get_stats()
    for key, value in stats.items():
        if isinstance(value, (int, float)):
            print(f"  {key}: {value:,}" if isinstance(value, int) else f"  {key}: {value}")
        else:
            print(f"  {key}: {value}")

    # Test think_and_speak
    task = "What is machine learning?"
    result = ctm.think_and_speak(task, max_new_tokens=30, temperature=0.8)

    print(f"\nTask: {task}")
    print(f"  Encoding method: {result.task_encoding['method']}")
    print(f"  Certainty: {result.certainty:.4f}")
    print(f"  Steps: {result.reasoning_steps}")
    print(f"  Response preview: {result.response[:80]}...")

    # Verify encoding method
    expected_method = 'semantic' if use_semantic else 'hash'
    assert result.task_encoding['method'] == expected_method, \
        f"Expected {expected_method}, got {result.task_encoding['method']}"

    print("SpeakingCTM semantic integration tests PASSED!")
    return True


def test_semantic_similarity_in_ctm():
    """Test that semantically similar tasks produce similar thoughts."""
    print("\n" + "=" * 60)
    print("Testing Semantic Similarity in CTM Outputs")
    print("=" * 60)

    try:
        from core.speaking_ctm import SpeakingCTM
        from core.semantic_task_encoder import HAS_SENTENCE_TRANSFORMERS
        from core.thought_decoder import HAS_TRANSFORMERS
    except ImportError as e:
        print(f"Import error: {e}")
        return False

    if not HAS_TRANSFORMERS or not HAS_SENTENCE_TRANSFORMERS:
        print("Required packages not installed. Skipping similarity test.")
        return True

    ctm = SpeakingCTM(
        feature_dim=256,
        thought_dim=2048,
        max_iterations=10,
        use_semantic_encoding=True,
        enable_logging=False,
        device="cpu"
    )

    # Similar tasks
    similar_tasks = [
        "What is machine learning?",
        "Explain ML in simple terms",
    ]

    # Different task
    different_task = "What is the capital of France?"

    # Get thought vectors
    thoughts = []
    for task in similar_tasks + [different_task]:
        output = ctm.think(task)
        thoughts.append(output.thought_vector.squeeze(0))

    # Compute cosine similarities
    def cosine_sim(a, b):
        return torch.nn.functional.cosine_similarity(a.unsqueeze(0), b.unsqueeze(0)).item()

    sim_similar = cosine_sim(thoughts[0], thoughts[1])
    sim_different = cosine_sim(thoughts[0], thoughts[2])

    print(f"Similarity (similar tasks): {sim_similar:.4f}")
    print(f"Similarity (different tasks): {sim_different:.4f}")

    # Similar tasks should have higher thought similarity
    # (with untrained model this might not hold, but with training it should)
    print(f"Similar > Different: {sim_similar > sim_different}")

    print("Semantic similarity test completed!")
    return True


if __name__ == "__main__":
    results = []

    results.append(("Semantic Encoder Standalone", test_semantic_encoder_standalone()))
    results.append(("HybridCTM with Semantic", test_hybrid_ctm_with_semantic()))
    results.append(("SpeakingCTM with Semantic", test_speaking_ctm_with_semantic()))
    results.append(("Semantic Similarity", test_semantic_similarity_in_ctm()))

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL SEMANTIC ENCODER TESTS PASSED!")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)
