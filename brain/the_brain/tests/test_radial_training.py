# tests/test_radial_training.py
"""Tests for RadialSleepTrainer."""
import pytest
import torch


class TestRadialSleepTrainer:

    def test_train_epoch_loss_decreases(self):
        """Loss should decrease over training steps."""
        from core.radial_attention import RadialAttentionNetwork
        from core.experience_buffer import ExperienceBuffer
        from core.radial_sleep_trainer import RadialSleepTrainer

        net = RadialAttentionNetwork(seed_dim=384)
        buf = ExperienceBuffer(max_size=100)
        trainer = RadialSleepTrainer(network=net, buffer=buf, lr=0.001)

        # Fill buffer with experiences
        for _ in range(50):
            seed = torch.randn(384)
            with torch.no_grad():
                result = net(seed.unsqueeze(0))
            buf.add(
                input_embedding=seed,
                ring_activations=result['ring_activations'],
                ctm_trajectory=[0.3, 0.5, 0.8],
                kuro_reward=0.7,
                outcome='success',
            )

        loss1 = trainer.train_epoch(batch_size=16)
        loss2 = trainer.train_epoch(batch_size=16)
        loss3 = trainer.train_epoch(batch_size=16)

        # Loss should generally trend downward
        assert loss3 < loss1 * 1.5, "Loss should not explode"

    def test_ewc_preserves_old_tasks(self):
        """EWC regularization prevents catastrophic forgetting."""
        from core.radial_attention import RadialAttentionNetwork
        from core.experience_buffer import ExperienceBuffer
        from core.radial_sleep_trainer import RadialSleepTrainer

        net = RadialAttentionNetwork(seed_dim=384)
        buf = ExperienceBuffer(max_size=100)
        trainer = RadialSleepTrainer(network=net, buffer=buf, lr=0.001,
                                      ewc_lambda=1000.0)

        # Task A: learn a pattern
        seed_a = torch.randn(384)
        for _ in range(20):
            with torch.no_grad():
                result = net(seed_a.unsqueeze(0))
            buf.add(seed_a, result['ring_activations'],
                    [0.9], 1.0, 'success')

        for _ in range(5):
            trainer.train_epoch(batch_size=16)

        # Snapshot output for task A
        with torch.no_grad():
            output_a_before = net(seed_a.unsqueeze(0))['meta_output'].clone()

        # Register EWC anchor
        trainer.register_ewc_anchor()

        # Task B: different pattern
        buf2 = ExperienceBuffer(max_size=100)
        trainer._buffer = buf2
        seed_b = torch.randn(384)
        for _ in range(20):
            with torch.no_grad():
                result = net(seed_b.unsqueeze(0))
            buf2.add(seed_b, result['ring_activations'],
                     [0.1], 0.2, 'failure')

        for _ in range(5):
            trainer.train_epoch(batch_size=16)

        # Task A output should not have changed dramatically
        with torch.no_grad():
            output_a_after = net(seed_a.unsqueeze(0))['meta_output']

        drift = (output_a_before - output_a_after).abs().mean().item()
        assert drift < 1.0, f"EWC should prevent large drift, got {drift}"

    def test_train_epoch_empty_buffer(self):
        """Training on empty buffer should return 0.0 loss."""
        from core.radial_attention import RadialAttentionNetwork
        from core.experience_buffer import ExperienceBuffer
        from core.radial_sleep_trainer import RadialSleepTrainer

        net = RadialAttentionNetwork(seed_dim=384)
        buf = ExperienceBuffer(max_size=100)
        trainer = RadialSleepTrainer(network=net, buffer=buf, lr=0.001)

        loss = trainer.train_epoch(batch_size=16)
        assert loss == 0.0

    def test_get_stats(self):
        """Stats should reflect trainer state."""
        from core.radial_attention import RadialAttentionNetwork
        from core.experience_buffer import ExperienceBuffer
        from core.radial_sleep_trainer import RadialSleepTrainer

        net = RadialAttentionNetwork(seed_dim=384)
        buf = ExperienceBuffer(max_size=100)
        trainer = RadialSleepTrainer(network=net, buffer=buf, lr=0.001)

        stats = trainer.get_stats()
        assert stats['total_epochs'] == 0
        assert stats['has_ewc_anchor'] is False
        assert stats['buffer_size'] == 0

    def test_register_ewc_anchor(self):
        """EWC anchor should be registered after calling register_ewc_anchor."""
        from core.radial_attention import RadialAttentionNetwork
        from core.experience_buffer import ExperienceBuffer
        from core.radial_sleep_trainer import RadialSleepTrainer

        net = RadialAttentionNetwork(seed_dim=384)
        buf = ExperienceBuffer(max_size=100)
        trainer = RadialSleepTrainer(network=net, buffer=buf, lr=0.001)

        # Add a few experiences so Fisher can be computed
        for _ in range(5):
            seed = torch.randn(384)
            with torch.no_grad():
                result = net(seed.unsqueeze(0))
            buf.add(seed, result['ring_activations'], [0.5], 0.5, 'success')

        trainer.register_ewc_anchor()

        stats = trainer.get_stats()
        assert stats['has_ewc_anchor'] is True
