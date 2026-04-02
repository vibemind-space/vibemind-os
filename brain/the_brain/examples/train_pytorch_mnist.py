"""
Train ATM-R with PyTorch on MNIST.

Example of end-to-end training with differentiable routing.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
from sklearn.datasets import fetch_openml
from sklearn.model_selection import train_test_split

from atmr_torch import ATMRClassifier


def load_mnist_torch(n_samples=5000, test_size=0.2, seed=42):
    """Load MNIST as PyTorch tensors."""
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

    # Convert to tensors
    return {
        'vision_train': torch.from_numpy(X_train_proj).float(),
        'audio_train': torch.from_numpy(audio_train).float(),
        'y_train': torch.from_numpy(y_train).long(),
        'vision_test': torch.from_numpy(X_test_proj).float(),
        'audio_test': torch.from_numpy(audio_test).float(),
        'y_test': torch.from_numpy(y_test).long()
    }


def train_epoch(model, loader, optimizer, device):
    """Train for one epoch."""
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch_idx, (vis, aud, labels) in enumerate(loader):
        vis, aud, labels = vis.to(device), aud.to(device), labels.to(device)
        batch_size = vis.shape[0]

        # Prepare multimodal input
        x = {
            'vision': vis,
            'audio': aud,
            'touch': torch.zeros(batch_size, 32, device=device),
            'taste': torch.zeros(batch_size, 16, device=device),
            'vestibular': torch.zeros(batch_size, 16, device=device),
            'threat': torch.zeros(batch_size, 8, device=device)
        }

        # Context: prefer vision
        ctx = torch.zeros(batch_size, 6, device=device)
        ctx[:, 0] = 1.0

        # Forward
        optimizer.zero_grad()
        logits = model(x, ctx=ctx)
        loss = F.cross_entropy(logits, labels)

        # Backward
        loss.backward()
        optimizer.step()

        # Stats
        total_loss += loss.item()
        pred = torch.argmax(logits, dim=1)
        correct += (pred == labels).sum().item()
        total += batch_size

        if batch_idx % 10 == 0:
            print(f"  Batch {batch_idx}/{len(loader)}: Loss={loss.item():.4f}")

    return total_loss / len(loader), correct / total


def evaluate(model, loader, device):
    """Evaluate model."""
    model.eval()
    correct = 0
    total = 0

    with torch.no_grad():
        for vis, aud, labels in loader:
            vis, aud, labels = vis.to(device), aud.to(device), labels.to(device)
            batch_size = vis.shape[0]

            x = {
                'vision': vis,
                'audio': aud,
                'touch': torch.zeros(batch_size, 32, device=device),
                'taste': torch.zeros(batch_size, 16, device=device),
                'vestibular': torch.zeros(batch_size, 16, device=device),
                'threat': torch.zeros(batch_size, 8, device=device)
            }

            ctx = torch.zeros(batch_size, 6, device=device)
            ctx[:, 0] = 1.0

            logits = model(x, ctx=ctx)
            pred = torch.argmax(logits, dim=1)
            correct += (pred == labels).sum().item()
            total += batch_size

    return correct / total


def main():
    print("=" * 60)
    print("ATM-R PyTorch Training on MNIST")
    print("=" * 60)

    # Config
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")

    n_samples = 5000
    batch_size = 32
    epochs = 5
    lr = 0.001

    # Load data
    data = load_mnist_torch(n_samples=n_samples)

    train_dataset = TensorDataset(
        data['vision_train'],
        data['audio_train'],
        data['y_train']
    )
    test_dataset = TensorDataset(
        data['vision_test'],
        data['audio_test'],
        data['y_test']
    )

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    print(f"Train size: {len(train_dataset)}, Test size: {len(test_dataset)}")

    # Create model
    print("\nCreating ATMRClassifier...")
    model = ATMRClassifier(
        num_classes=10,
        adaptive=True,
        hidden_dim=128,
        device=device
    )

    # Optimizer
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    # Train
    print("\nTraining...")
    for epoch in range(epochs):
        print(f"\nEpoch {epoch+1}/{epochs}")
        train_loss, train_acc = train_epoch(model, train_loader, optimizer, device)
        test_acc = evaluate(model, test_loader, device)

        print(f"  Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.4f}")
        print(f"  Test Acc: {test_acc:.4f}")

        # Show gates
        gates = model.get_gates()
        print(f"  Current gates: {gates.detach().cpu().numpy()}")

    print("\n" + "=" * 60)
    print("Training complete!")
    print("=" * 60)

    # Save model
    torch.save(model.state_dict(), 'atmr_mnist.pth')
    print("\nModel saved to atmr_mnist.pth")


if __name__ == "__main__":
    main()
