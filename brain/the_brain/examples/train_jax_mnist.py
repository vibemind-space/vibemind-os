"""
Train ATM-R with JAX/Flax on MNIST.

Demonstrates JIT compilation and vmap for fast training.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import jax
import jax.numpy as jnp
from jax import random, jit, vmap
import optax
from flax.training import train_state
import numpy as np
from sklearn.datasets import fetch_openml
from sklearn.model_selection import train_test_split
import time

from atmr_jax import ATMRClassifier
from config_loader import load_config


def load_mnist_jax(n_samples=5000, test_size=0.2, seed=42):
    """Load MNIST as JAX arrays."""
    print("Loading MNIST...")
    mnist = fetch_openml('mnist_784', version=1, parser='auto')
    X, y = mnist['data'].values[:n_samples], mnist['target'].values[:n_samples].astype(int)

    # Normalize
    X = X / 255.0

    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=seed)

    # Project to ATM-R vision dimension (128)
    np.random.seed(seed)
    proj_matrix = np.random.randn(128, 784) / np.sqrt(784)
    X_train_proj = (proj_matrix @ X_train.T).T
    X_test_proj = (proj_matrix @ X_test.T).T

    # Generate synthetic audio
    def gen_audio(label):
        freq = 0.1 + label * 0.05
        t = np.linspace(0, 2*np.pi, 64)
        return np.sin(freq * t) + 0.1 * np.random.randn(64)

    audio_train = np.array([gen_audio(l) for l in y_train])
    audio_test = np.array([gen_audio(l) for l in y_test])

    # Convert to JAX arrays
    return {
        'vision_train': jnp.array(X_train_proj),
        'audio_train': jnp.array(audio_train),
        'y_train': jnp.array(y_train),
        'vision_test': jnp.array(X_test_proj),
        'audio_test': jnp.array(audio_test),
        'y_test': jnp.array(y_test)
    }


def create_train_state(model, rng, learning_rate, input_shape):
    """Create initial training state."""
    # Dummy input for initialization
    dummy_x = {
        'vision': jnp.ones((1, 128)),
        'audio': jnp.ones((1, 64)),
        'touch': jnp.zeros((1, 32)),
        'taste': jnp.zeros((1, 16)),
        'vestibular': jnp.zeros((1, 16)),
        'threat': jnp.zeros((1, 8))
    }

    variables = model.init(rng, dummy_x)
    tx = optax.adam(learning_rate)

    return train_state.TrainState.create(
        apply_fn=model.apply,
        params=variables['params'],
        tx=tx
    )


@jit
def train_step(state, batch, ctx):
    """Single training step (JIT-compiled)."""
    x, y = batch

    def loss_fn(params):
        logits = state.apply_fn({'params': params}, x, ctx, training=True)
        loss = optax.softmax_cross_entropy_with_integer_labels(logits, y).mean()
        return loss, logits

    grad_fn = jax.value_and_grad(loss_fn, has_aux=True)
    (loss, logits), grads = grad_fn(state.params)
    state = state.apply_gradients(grads=grads)

    accuracy = jnp.mean(jnp.argmax(logits, axis=-1) == y)
    return state, loss, accuracy


@jit
def eval_step(state, batch, ctx):
    """Single eval step (JIT-compiled)."""
    x, y = batch

    logits = state.apply_fn({'params': state.params}, x, ctx, training=False)
    loss = optax.softmax_cross_entropy_with_integer_labels(logits, y).mean()
    accuracy = jnp.mean(jnp.argmax(logits, axis=-1) == y)

    return loss, accuracy


def create_batches(data, batch_size, shuffle_rng=None):
    """Create batches from data."""
    n_samples = data['vision_train'].shape[0]
    indices = jnp.arange(n_samples)

    if shuffle_rng is not None:
        indices = random.permutation(shuffle_rng, indices)

    for start_idx in range(0, n_samples, batch_size):
        end_idx = min(start_idx + batch_size, n_samples)
        batch_indices = indices[start_idx:end_idx]

        batch_x = {
            'vision': data['vision_train'][batch_indices],
            'audio': data['audio_train'][batch_indices],
            'touch': jnp.zeros((len(batch_indices), 32)),
            'taste': jnp.zeros((len(batch_indices), 16)),
            'vestibular': jnp.zeros((len(batch_indices), 16)),
            'threat': jnp.zeros((len(batch_indices), 8))
        }
        batch_y = data['y_train'][batch_indices]

        yield (batch_x, batch_y)


def main():
    print("=" * 60)
    print("ATM-R JAX Training on MNIST")
    print("=" * 60)

    # Config
    n_samples = 5000
    batch_size = 32
    epochs = 5
    learning_rate = 0.001
    seed = 42

    # Load data
    data = load_mnist_jax(n_samples=n_samples, seed=seed)
    print(f"Train size: {data['vision_train'].shape[0]}, Test size: {data['vision_test'].shape[0]}")

    # Create model
    print("\nCreating ATMRClassifier...")
    config = load_config('configs/default.yaml')
    model = ATMRClassifier(config=config, num_classes=10, hidden_dim=128)

    # Initialize
    rng = random.PRNGKey(seed)
    rng, init_rng = random.split(rng)

    state = create_train_state(model, init_rng, learning_rate, input_shape=(128,))
    print(f"Model initialized with {sum(x.size for x in jax.tree.leaves(state.params))} parameters")

    # Context: prefer vision
    ctx_train = jnp.zeros((batch_size, 6))
    ctx_train = ctx_train.at[:, 0].set(1.0)

    # Training loop
    print("\nTraining...")
    for epoch in range(epochs):
        print(f"\nEpoch {epoch + 1}/{epochs}")

        rng, shuffle_rng = random.split(rng)

        # Train
        epoch_loss = []
        epoch_acc = []
        start_time = time.time()

        for batch in create_batches(data, batch_size, shuffle_rng):
            # Pad ctx if batch size is smaller
            actual_batch_size = batch[0]['vision'].shape[0]
            if actual_batch_size < batch_size:
                ctx_batch = jnp.zeros((actual_batch_size, 6))
                ctx_batch = ctx_batch.at[:, 0].set(1.0)
            else:
                ctx_batch = ctx_train

            state, loss, acc = train_step(state, batch, ctx_batch)
            epoch_loss.append(loss)
            epoch_acc.append(acc)

        train_time = time.time() - start_time

        # Eval
        test_batch_size = 100
        test_batches = data['vision_test'].shape[0] // test_batch_size
        test_losses = []
        test_accs = []

        for i in range(test_batches):
            start_idx = i * test_batch_size
            end_idx = start_idx + test_batch_size

            test_x = {
                'vision': data['vision_test'][start_idx:end_idx],
                'audio': data['audio_test'][start_idx:end_idx],
                'touch': jnp.zeros((test_batch_size, 32)),
                'taste': jnp.zeros((test_batch_size, 16)),
                'vestibular': jnp.zeros((test_batch_size, 16)),
                'threat': jnp.zeros((test_batch_size, 8))
            }
            test_y = data['y_test'][start_idx:end_idx]
            ctx_test = jnp.zeros((test_batch_size, 6))
            ctx_test = ctx_test.at[:, 0].set(1.0)

            test_loss, test_acc = eval_step(state, (test_x, test_y), ctx_test)
            test_losses.append(test_loss)
            test_accs.append(test_acc)

        print(f"  Train Loss: {np.mean(epoch_loss):.4f}, Train Acc: {np.mean(epoch_acc):.4f}")
        print(f"  Test Loss: {np.mean(test_losses):.4f}, Test Acc: {np.mean(test_accs):.4f}")
        print(f"  Time: {train_time:.2f}s")

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)

    # Show JIT compilation speedup
    print("\nBenchmarking JIT speedup...")
    rng, bench_rng = random.split(rng)
    bench_batch = next(create_batches(data, batch_size, bench_rng))

    # Warm up
    for _ in range(5):
        state, _, _ = train_step(state, bench_batch, ctx_train)

    # Time JIT-compiled version
    start = time.time()
    for _ in range(100):
        state, _, _ = train_step(state, bench_batch, ctx_train)
    jit_time = time.time() - start

    print(f"  100 JIT-compiled steps: {jit_time:.4f}s")
    print(f"  Steps/sec: {100/jit_time:.1f}")


if __name__ == "__main__":
    main()
