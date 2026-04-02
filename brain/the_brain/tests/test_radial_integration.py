"""End-to-end integration test for Radial Attention Network."""
import pytest
import torch


class TestRadialIntegration:

    def test_full_cycle_wake_and_sleep(self):
        """Full cycle: wake (forward + hebbian) -> sleep (backprop)."""
        from core.radial_attention import RadialAttentionNetwork
        from core.hebbian_plasticity import HebbianAttentionUpdate
        from core.experience_buffer import ExperienceBuffer
        from core.radial_sleep_trainer import RadialSleepTrainer

        # Setup
        net = RadialAttentionNetwork(seed_dim=384)
        hebb = HebbianAttentionUpdate()
        buf = ExperienceBuffer(max_size=100)
        trainer = RadialSleepTrainer(net, buf)

        # WAKE: Process 20 inputs
        for _ in range(20):
            seed = torch.randn(1, 384)
            result = net(seed)

            # Hebbian update between Ring 1 and Ring 2
            hebb.update(
                net.rings[0],
                result['ring_activations'][0],
                result['ring_activations'][1],
            )

            # Collect experience
            buf.add(
                input_embedding=seed.squeeze(0),
                ring_activations=result['ring_activations'],
                ctm_trajectory=[0.3, 0.5, 0.7, 0.85, 0.92],
                kuro_reward=0.6,
                outcome='success',
            )

        assert len(buf) == 20
        assert hebb._total_updates == 20

        # SLEEP: Train 3 epochs
        losses = []
        for _ in range(3):
            loss = trainer.train_epoch(batch_size=10)
            losses.append(loss)

        assert all(l >= 0 for l in losses)
        assert trainer._total_epochs == 3

    def test_dual_process_with_radial(self):
        """Dual process: System 1 (mock) vs System 2 (radial)."""
        from core.radial_attention import RadialAttentionNetwork, DualProcessRouter

        net = RadialAttentionNetwork(seed_dim=384)
        router = DualProcessRouter(dim=128)

        seed = torch.randn(1, 384)
        radial_result = net(seed)
        system2 = radial_result['meta_output']

        # Mock System 1 as a simple projection
        system1 = torch.randn(1, 128)

        decision = router(system1, system2)
        assert decision['system_used'] in (1, 2)
        assert 'output' in decision
