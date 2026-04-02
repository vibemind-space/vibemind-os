"""Tests for experience replay buffer."""
import pytest
import torch
import time


class TestExperienceBuffer:

    def test_add_and_size(self):
        from core.experience_buffer import ExperienceBuffer
        buf = ExperienceBuffer(max_size=100)
        buf.add(input_embedding=torch.randn(384),
                ring_activations=[torch.randn(d) for d in [64, 128, 256, 256, 128]],
                ctm_trajectory=[0.3, 0.5, 0.7],
                kuro_reward=0.8,
                outcome='success')
        assert len(buf) == 1

    def test_overflow_drops_oldest(self):
        from core.experience_buffer import ExperienceBuffer
        buf = ExperienceBuffer(max_size=5)
        for i in range(10):
            buf.add(input_embedding=torch.randn(384),
                    ring_activations=[],
                    ctm_trajectory=[float(i)],
                    kuro_reward=float(i),
                    outcome='ok')
        assert len(buf) == 5
        # Oldest (i=0..4) should be gone, newest (i=5..9) present
        assert buf._buffer[0]['kuro_reward'] == 5.0

    def test_sample_batch(self):
        from core.experience_buffer import ExperienceBuffer
        buf = ExperienceBuffer(max_size=100)
        for _ in range(20):
            buf.add(input_embedding=torch.randn(384),
                    ring_activations=[torch.randn(d) for d in [64, 128, 256, 256, 128]],
                    ctm_trajectory=[0.5],
                    kuro_reward=0.5,
                    outcome='ok')
        batch = buf.sample(batch_size=8)
        assert len(batch) == 8

    def test_sample_larger_than_buffer(self):
        """Sampling more than buffer size returns all items."""
        from core.experience_buffer import ExperienceBuffer
        buf = ExperienceBuffer(max_size=100)
        for _ in range(3):
            buf.add(input_embedding=torch.randn(384),
                    ring_activations=[],
                    ctm_trajectory=[0.1],
                    kuro_reward=0.5,
                    outcome='ok')
        batch = buf.sample(batch_size=10)
        assert len(batch) == 3

    def test_get_stats(self):
        """Stats track total added vs current size."""
        from core.experience_buffer import ExperienceBuffer
        buf = ExperienceBuffer(max_size=5)
        for i in range(10):
            buf.add(input_embedding=torch.randn(384),
                    ring_activations=[],
                    ctm_trajectory=[float(i)],
                    kuro_reward=float(i),
                    outcome='ok')
        stats = buf.get_stats()
        assert stats['buffer_size'] == 5
        assert stats['total_added'] == 10
        assert stats['max_size'] == 5

    def test_empty_buffer_sample(self):
        """Sampling from empty buffer returns empty list."""
        from core.experience_buffer import ExperienceBuffer
        buf = ExperienceBuffer(max_size=100)
        batch = buf.sample(batch_size=5)
        assert len(batch) == 0

    def test_tensors_detached_and_cpu(self):
        """Stored tensors should be detached and on CPU."""
        from core.experience_buffer import ExperienceBuffer
        buf = ExperienceBuffer(max_size=100)
        t = torch.randn(384, requires_grad=True)
        buf.add(input_embedding=t,
                ring_activations=[torch.randn(64, requires_grad=True)],
                ctm_trajectory=[0.5],
                kuro_reward=0.5,
                outcome='ok')
        stored = buf._buffer[0]
        assert not stored['input_embedding'].requires_grad
        assert not stored['ring_activations'][0].requires_grad
        assert stored['input_embedding'].device.type == 'cpu'
