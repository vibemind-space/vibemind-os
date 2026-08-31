# Neural Manifold Thought Visualization

**Date:** 2026-02-24
**Status:** Approved
**Depends on:** ThoughtEvolutionEngine (f27c308+), klotskipuzzle CTM integration

## Problem

The ThoughtEvolutionEngine generates 384-dim semantic embeddings for each thought, builds a semantic graph (parent/similar edges), and computes fitness scores. Currently, this data is only exposed as flat JSON lists via `/api/cortex/thought-graph`. There is no spatial visualization that shows how knowledge organizes in semantic space.

The human brain organizes abstract knowledge on low-dimensional neural manifolds (hippocampal grid cells, Nobel Prize 2014). We want to replicate this: project the thought embeddings onto a 3D manifold where distance = semantic dissimilarity, and visualize the attractor landscape.

## Architecture

### 1. Data Pipeline (Backend)

```
ThoughtEvolutionEngine._embeddings  Dict[str, np.ndarray(384)]
        |
   UMAP Reducer (384-dim -> 3-dim)
   - n_neighbors=15, min_dist=0.1, metric='cosine'
   - Incremental: new thoughts projected via transform()
        |
   DBSCAN Cluster Detection (eps=0.5, min_samples=3)
   - Identifies "attractor basins" (semantic concept groups)
        |
   GET /api/cortex/thought-manifold
   Returns: {nodes, edges, clusters, stats}
```

**Why UMAP over t-SNE:** Preserves global structure (distant points stay distant), supports incremental projection, 10-100x faster at N=100.

**Why UMAP over PCA:** Semantic similarity is non-linear. Embedding spaces have curved manifolds that PCA cannot capture.

### 2. API Endpoint

New endpoint: `GET /api/cortex/thought-manifold`

Response:
```json
{
  "nodes": [
    {
      "id": "a1b2c3d4",
      "x": 1.23, "y": 2.45, "z": -0.89,
      "fitness": 0.742,
      "generation": 3,
      "category": "evolve",
      "content": "First 100 chars...",
      "cluster_id": 0,
      "consciousness": 0.0
    }
  ],
  "edges": [
    {"source": "a1b2c3d4", "target": "e5f6g7h8", "type": "parent"},
    {"source": "a1b2c3d4", "target": "i9j0k1l2", "type": "similar"}
  ],
  "clusters": [
    {
      "id": 0,
      "center_x": 1.5, "center_y": 2.0, "center_z": -0.5,
      "size": 12,
      "avg_fitness": 0.65,
      "dominant_topic": "physics"
    }
  ],
  "stats": {
    "total_nodes": 47,
    "total_clusters": 3,
    "avg_fitness": 0.62,
    "max_generation": 5,
    "manifold_stress": 0.15
  }
}
```

### 3. CTM Integration (Phase 2)

Adapter layer projects 384-dim thought embeddings into CTM's 256-dim feature space:

```python
class ThoughtCTMAdapter(nn.Module):
    def __init__(self):
        self.projection = nn.Linear(384, 256)
        self.norm = nn.LayerNorm(256)

    def forward(self, thought_embeddings):  # [N, 384]
        return self.norm(self.projection(thought_embeddings))  # [N, 256]
```

CTM learns on thought data:
- **Fitness prediction**: Given embedding, predict fitness (MSE loss against actual critic+user fitness)
- **Consciousness convergence**: Iterative reasoning over thought clusters
- **Module activations**: Which brain modules (VIS, DLPFC, MTL...) activate for which thought types

Training signal: Evolution fitness scores serve as automatic labels.

### 4. 3D Visualization (Three.js in Moltbook)

New tab "Manifold" in moltbook_dashboard.html.

Visual encoding:

| Property | Encoding |
|----------|----------|
| Position (x,y,z) | UMAP from 384-dim embedding |
| Y-axis offset | Fitness (higher = fitter, attractor landscape) |
| Color | Generation (blue=gen-0, yellow=gen-2, red=gen-5+) |
| Size | Sphere radius scales with CTM consciousness (Phase 2) |
| Opacity | Age (newer = brighter) |
| White thin lines | `similar` edges |
| Green thick lines | `parent` edges (evolution lineage) |
| Hover | Tooltip with content, fitness, generation |
| Click | Inline slider rating |

Auto-refresh every 10s (matches CTE idle interval).

### 5. Cluster Detection (Attractor Basins)

DBSCAN on the 3D UMAP coordinates identifies semantic clusters automatically:

```python
from sklearn.cluster import DBSCAN

clusters = DBSCAN(eps=0.5, min_samples=3).fit(coords_3d)
```

These clusters represent "attractor basins" in the neural manifold:
- Dense clusters = well-developed knowledge areas
- Sparse areas = knowledge gaps
- Bridges between clusters = cross-domain connections (valuable for evolution)

Y-axis is further offset by fitness to create a landscape topology:
- Peaks = high-fitness thought clusters (well-understood)
- Valleys = low-fitness regions (needs more learning)

## Dependencies

- `umap-learn` (pip install umap-learn)
- `scikit-learn` (DBSCAN, already available)
- `three.js` (CDN, already used in klotskipuzzle)
- `OrbitControls` (Three.js addon for camera control)

## Files to Create/Modify

| File | Action |
|------|--------|
| `core/brain_chat.py` | Add `get_manifold()` to ThoughtEvolutionEngine |
| `core/thought_ctm_adapter.py` | New: ThoughtCTMAdapter (Phase 2) |
| `web/routers/cortex.py` | Add `GET /api/cortex/thought-manifold` |
| `web/templates/moltbook_dashboard.html` | Add "Manifold" tab with Three.js canvas |
| `web/static/js/manifold-viewer.js` | New: Three.js 3D renderer |
| `tests/test_brain_chat_quick.py` | Tests for get_manifold(), UMAP, DBSCAN |

## Neuroscience Rationale

This design is inspired by:
1. **Hippocampal grid cells** (Moser & Moser, 2014): Abstract knowledge organized in metric spaces
2. **Attractor dynamics** (Hopfield, 1982): Memories as stable states in energy landscapes
3. **Neural manifolds** (Gallego et al., 2017): Brain activity constrained to low-dimensional manifolds
4. **Hebbian plasticity**: "Neurons that fire together wire together" = our semantic similarity edges
5. **Sleep consolidation**: Raw thoughts compressed to abstract clusters = our evolution crossover
