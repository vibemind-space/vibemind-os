"""
Logging and visualization utilities for ATM-R.

Features:
- CSV logging for gates, latents, parameters
- Plotting: gate timelines, latent trajectories, parameter evolution
- Metrics: purity, switch latency, energy, stability
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import cm
from mpl_toolkits.mplot3d import Axes3D
from sklearn.decomposition import PCA
import os
from typing import Dict, List, Optional, Union


class ATMRLogger:
    """Logger for ATM-R simulation data."""

    def __init__(
        self,
        log_dir: str = "data",
        save_interval: int = 10,
        csv_format: bool = True
    ):
        """
        Initialize logger.

        Args:
            log_dir: Directory to save logs
            save_interval: Save to CSV every N steps
            csv_format: Enable CSV logging
        """
        self.log_dir = log_dir
        self.save_interval = save_interval
        self.csv_format = csv_format

        os.makedirs(log_dir, exist_ok=True)

        # Storage
        self.history = {
            'timestep': [],
            'gates': [],
            'pe': [],
            'latents': [],
            'params': [],
            'adapted': []
        }

    def log_step(
        self,
        t: int,
        g: np.ndarray,
        pe: Dict[str, float],
        v: Dict[str, np.ndarray],
        params: Optional[Dict] = None,
        adapted: Optional[Dict] = None
    ):
        """
        Log a single time step.

        Args:
            t: timestep
            g: gate weights (M-dim)
            pe: prediction errors
            v: latent states
            params: model parameters (tau, priors, etc.)
            adapted: adapted parameters (if adaptive model)
        """
        self.history['timestep'].append(t)
        self.history['gates'].append(g.copy())
        self.history['pe'].append(pe.copy())
        self.history['latents'].append({k: v_i.copy() for k, v_i in v.items()})

        if params is not None:
            self.history['params'].append(params.copy())
        if adapted is not None:
            self.history['adapted'].append(adapted.copy())

        # Save to CSV periodically
        if self.csv_format and t % self.save_interval == 0:
            self.save_csv()

    def save_csv(self):
        """Save logged data to CSV files."""
        if len(self.history['timestep']) == 0:
            return

        # Gates
        gates_df = pd.DataFrame(
            self.history['gates'],
            columns=[f"g_{i}" for i in range(len(self.history['gates'][0]))]
        )
        gates_df.insert(0, 'timestep', self.history['timestep'])
        gates_df.to_csv(os.path.join(self.log_dir, 'gates.csv'), index=False)

        # Prediction errors
        pe_df = pd.DataFrame(self.history['pe'])
        pe_df.insert(0, 'timestep', self.history['timestep'])
        pe_df.to_csv(os.path.join(self.log_dir, 'prediction_errors.csv'), index=False)

        # Parameters (if logged)
        if len(self.history['params']) > 0:
            # Extract tau, priors, gate_temp
            params_data = []
            for p in self.history['params']:
                row = {}
                if 'tau' in p:
                    for k, v in p['tau'].items():
                        row[f'tau_{k}'] = v
                if 'priors' in p:
                    for k, v in p['priors'].items():
                        row[f'prior_{k}'] = v
                if 'gate_temp' in p:
                    row['gate_temp'] = p['gate_temp']
                params_data.append(row)

            params_df = pd.DataFrame(params_data)
            params_df.insert(0, 'timestep', self.history['timestep'][:len(params_data)])
            params_df.to_csv(os.path.join(self.log_dir, 'parameters.csv'), index=False)

        print(f"Saved logs to {self.log_dir}")

    def get_dataframe(self, key: str = 'gates') -> pd.DataFrame:
        """Get history as DataFrame."""
        if key == 'gates':
            df = pd.DataFrame(
                self.history['gates'],
                columns=[f"g_{i}" for i in range(len(self.history['gates'][0]))]
            )
            df.insert(0, 'timestep', self.history['timestep'])
            return df
        elif key == 'pe':
            df = pd.DataFrame(self.history['pe'])
            df.insert(0, 'timestep', self.history['timestep'])
            return df
        else:
            raise ValueError(f"Unknown key: {key}")


class ATMRVisualizer:
    """Visualization utilities for ATM-R."""

    @staticmethod
    def plot_gates(
        logger: ATMRLogger,
        modalities: List[str],
        save_path: Optional[str] = None,
        figsize: tuple = (12, 6)
    ):
        """
        Plot gate weights over time.

        Args:
            logger: ATMRLogger instance
            modalities: List of modality names
            save_path: Path to save figure (or None to display)
            figsize: Figure size
        """
        gates_df = logger.get_dataframe('gates')
        timesteps = gates_df['timestep'].values

        fig, ax = plt.subplots(figsize=figsize)

        colors = cm.tab10(np.linspace(0, 1, len(modalities)))
        for i, (mod, color) in enumerate(zip(modalities, colors)):
            ax.plot(timesteps, gates_df[f'g_{i}'].values, label=mod, color=color, linewidth=2)

        ax.set_xlabel('Time step', fontsize=12)
        ax.set_ylabel('Gate weight', fontsize=12)
        ax.set_title('ATM-R Gate Dynamics', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(alpha=0.3)

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"Saved gate plot to {save_path}")
        else:
            plt.show()

        plt.close()

    @staticmethod
    def plot_latent_trajectory_3d(
        logger: ATMRLogger,
        modality: str,
        modalities: List[str],
        save_path: Optional[str] = None,
        figsize: tuple = (10, 8)
    ):
        """
        Plot 3D trajectory of latent states (PCA projection).

        Args:
            logger: ATMRLogger instance
            modality: Which modality to plot
            modalities: List of modality names
            save_path: Path to save figure
            figsize: Figure size
        """
        latents = logger.history['latents']
        if len(latents) == 0:
            print("No latent data to plot")
            return

        # Extract latent vectors for this modality
        v_history = np.array([lat[modality] for lat in latents])

        if v_history.shape[1] < 3:
            print(f"Modality {modality} has dim < 3, cannot plot 3D")
            return

        # PCA to 3D
        if v_history.shape[1] > 3:
            pca = PCA(n_components=3)
            v_3d = pca.fit_transform(v_history)
        else:
            v_3d = v_history[:, :3]

        # Color by time
        timesteps = logger.history['timestep']
        colors = np.array(timesteps) / max(timesteps)

        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111, projection='3d')

        scatter = ax.scatter(
            v_3d[:, 0], v_3d[:, 1], v_3d[:, 2],
            c=colors, cmap='viridis', s=20, alpha=0.6
        )

        ax.plot(v_3d[:, 0], v_3d[:, 1], v_3d[:, 2], 'k-', alpha=0.3, linewidth=0.5)

        ax.set_xlabel('PC1', fontsize=10)
        ax.set_ylabel('PC2', fontsize=10)
        ax.set_zlabel('PC3', fontsize=10)
        ax.set_title(f'Latent Trajectory: {modality}', fontsize=12, fontweight='bold')

        cbar = plt.colorbar(scatter, ax=ax, pad=0.1)
        cbar.set_label('Time', fontsize=10)

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"Saved 3D trajectory to {save_path}")
        else:
            plt.show()

        plt.close()

    @staticmethod
    def plot_parameter_evolution(
        logger: ATMRLogger,
        param_name: str,
        modalities: List[str],
        save_path: Optional[str] = None,
        figsize: tuple = (12, 6)
    ):
        """
        Plot evolution of a parameter (tau, priors, etc.) over time.

        Args:
            logger: ATMRLogger instance
            param_name: 'tau', 'prior', or 'gate_temp'
            modalities: List of modality names
            save_path: Path to save figure
            figsize: Figure size
        """
        if len(logger.history['params']) == 0:
            print("No parameter history to plot")
            return

        params_df = pd.read_csv(os.path.join(logger.log_dir, 'parameters.csv'))
        timesteps = params_df['timestep'].values

        fig, ax = plt.subplots(figsize=figsize)

        if param_name == 'gate_temp':
            ax.plot(timesteps, params_df['gate_temp'].values, label='gate_temp', linewidth=2)
        else:
            colors = cm.tab10(np.linspace(0, 1, len(modalities)))
            for mod, color in zip(modalities, colors):
                col = f'{param_name}_{mod}'
                if col in params_df.columns:
                    ax.plot(timesteps, params_df[col].values, label=mod, color=color, linewidth=2)

        ax.set_xlabel('Time step', fontsize=12)
        ax.set_ylabel(param_name, fontsize=12)
        ax.set_title(f'Parameter Evolution: {param_name}', fontsize=14, fontweight='bold')
        ax.legend(loc='best')
        ax.grid(alpha=0.3)

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"Saved parameter plot to {save_path}")
        else:
            plt.show()

        plt.close()


class ATMRMetrics:
    """Compute metrics for ATM-R performance."""

    @staticmethod
    def routing_purity(g: np.ndarray) -> float:
        """
        Compute routing purity: max_i g_i.

        Measures how decisively the system selects a single modality.

        Args:
            g: gate weights (M-dim)

        Returns:
            purity in [0, 1]
        """
        return np.max(g)

    @staticmethod
    def gate_entropy(g: np.ndarray) -> float:
        """
        Compute gate entropy in bits.

        Args:
            g: gate weights (M-dim)

        Returns:
            entropy in bits
        """
        return -np.sum(g * np.log2(g + 1e-10))

    @staticmethod
    def energy_proxy(g: np.ndarray, threshold: float = 0.1) -> float:
        """
        Compute energy proxy: fraction of suppressed channels.

        Args:
            g: gate weights (M-dim)
            threshold: gates below this are considered suppressed

        Returns:
            fraction of suppressed gates
        """
        return np.mean(g < threshold)

    @staticmethod
    def stability(gate_history: np.ndarray, window: int = 10) -> float:
        """
        Compute gate stability: inverse of variance over a window.

        Args:
            gate_history: T×M array of gates over time
            window: window size for variance computation

        Returns:
            mean inverse variance
        """
        if len(gate_history) < window:
            return 0.0

        variances = []
        for i in range(len(gate_history) - window + 1):
            window_gates = gate_history[i:i+window]
            variances.append(np.var(window_gates, axis=0).mean())

        return 1.0 / (np.mean(variances) + 1e-6)

    @staticmethod
    def switch_latency(
        gate_history: np.ndarray,
        switch_time: int,
        target_modality: int,
        threshold: float = 0.5
    ) -> int:
        """
        Compute switch latency: time from switch_time until target_modality becomes dominant.

        Args:
            gate_history: T×M array
            switch_time: time of context/hazard change
            target_modality: index of expected dominant modality
            threshold: gate value considered dominant

        Returns:
            latency in time steps (-1 if never achieved)
        """
        for t in range(switch_time, len(gate_history)):
            if gate_history[t, target_modality] >= threshold:
                return t - switch_time
        return -1  # never achieved


# Example usage
if __name__ == "__main__":
    # Demo with synthetic data
    logger = ATMRLogger(log_dir="data/demo")

    modalities = ["vision", "audio", "touch", "taste", "vestibular", "threat"]
    M = len(modalities)

    # Simulate 100 steps
    for t in range(100):
        # Synthetic gates: vision dominates, then threat takes over at t=50
        if t < 50:
            g = np.array([0.6, 0.1, 0.1, 0.05, 0.1, 0.05])
        else:
            g = np.array([0.1, 0.1, 0.1, 0.05, 0.1, 0.55])

        pe = {m: np.random.rand() for m in modalities}
        v = {m: np.random.randn(16) for m in modalities}

        logger.log_step(t, g, pe, v)

    logger.save_csv()

    # Plot gates
    ATMRVisualizer.plot_gates(logger, modalities, save_path="data/demo/gates.png")

    # Compute metrics
    gates_array = np.array(logger.history['gates'])
    print(f"Mean purity: {np.mean([ATMRMetrics.routing_purity(g) for g in gates_array]):.3f}")
    print(f"Mean entropy: {np.mean([ATMRMetrics.gate_entropy(g) for g in gates_array]):.3f} bits")
    print(f"Switch latency (t=50): {ATMRMetrics.switch_latency(gates_array, 50, 5, 0.5)} steps")
