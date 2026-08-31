# Neural Manifold Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 3D UMAP-based thought visualization with attractor-basin clustering to the Moltbook dashboard.

**Architecture:** ThoughtEvolutionEngine gets a `get_manifold()` method that runs UMAP (384-dim to 3-dim) + DBSCAN clustering on cached embeddings. A new API endpoint serves the 3D data. A Three.js canvas in a new "Manifold" tab renders the point cloud with edges, color-coded by generation and y-offset by fitness.

**Tech Stack:** umap-learn, scikit-learn (DBSCAN), Three.js (CDN), OrbitControls (CDN)

---

## Task 1: Install dependencies

**Files:** None (pip only)

**Step 1: Install umap-learn**

Run: `pip install umap-learn`
Expected: Successfully installed umap-learn, numba, pynndescent

**Step 2: Verify imports work**

Run: `python -c "import umap; from sklearn.cluster import DBSCAN; print('OK')"`
Expected: `OK`

**Step 3: Commit requirements update**

Run:
```bash
pip freeze | grep -iE "umap|numba|pynndescent" >> requirements.txt
git add requirements.txt
git commit -m "deps: add umap-learn for neural manifold projection"
```

---

## Task 2: Write failing tests for get_manifold()

**Files:**
- Test: `tests/test_brain_chat_quick.py` (append to end)

**Step 1: Write the failing tests**

Append to `tests/test_brain_chat_quick.py` after the `TestEvolutionIntegration` class:

```python
class TestNeuralManifold:
    """Test UMAP 3D projection and DBSCAN clustering."""

    def test_get_manifold_empty(self):
        """Returns empty manifold when no embeddings."""
        evo = ThoughtEvolutionEngine()
        m = evo.get_manifold()
        assert m['nodes'] == []
        assert m['edges'] == []
        assert m['clusters'] == []
        assert m['stats']['total_nodes'] == 0

    def test_get_manifold_too_few(self):
        """With < 5 thoughts, returns nodes but no UMAP (raw positions)."""
        idx = _MockSemanticIndex()
        evo = ThoughtEvolutionEngine(semantic_index=idx)
        for i in range(3):
            t = _make_thought(thought_id=f"mf{i}", content=f"Manifold thought {i}")
            evo.ingest(t)
        m = evo.get_manifold()
        assert len(m['nodes']) == 3
        # Without UMAP, nodes should still have x, y, z coordinates
        for node in m['nodes']:
            assert 'x' in node and 'y' in node and 'z' in node

    def test_get_manifold_with_umap(self):
        """With >= 5 thoughts, UMAP projects to 3D."""
        idx = _MockSemanticIndex()
        evo = ThoughtEvolutionEngine(semantic_index=idx)
        for i in range(10):
            t = _make_thought(
                thought_id=f"mu{i}",
                content=f"Unique thought about topic number {i} in science",
            )
            evo.ingest(t)
            evo._critic_scores[f"mu{i}"] = 0.3 + i * 0.07
        m = evo.get_manifold()
        assert len(m['nodes']) == 10
        # Verify 3D coords exist
        for node in m['nodes']:
            assert isinstance(node['x'], float)
            assert isinstance(node['y'], float)
            assert isinstance(node['z'], float)
            assert 'fitness' in node
            assert 'generation' in node

    def test_get_manifold_includes_edges(self):
        """Manifold response includes graph edges."""
        idx = _MockSemanticIndex()
        evo = ThoughtEvolutionEngine(semantic_index=idx)
        for i in range(5):
            t = _make_thought(thought_id=f"me{i}", content=f"Edge thought {i}")
            evo.ingest(t)
        evo._graph_edges["me0"]["me1"] = "similar"
        m = evo.get_manifold()
        assert len(m['edges']) >= 1

    def test_get_manifold_includes_clusters(self):
        """DBSCAN finds clusters when thoughts are similar."""
        idx = _MockSemanticIndex()
        evo = ThoughtEvolutionEngine(semantic_index=idx)
        # Create 10 thoughts - DBSCAN may or may not cluster them
        for i in range(10):
            t = _make_thought(thought_id=f"mc{i}", content=f"Cluster thought {i}")
            evo.ingest(t)
        m = evo.get_manifold()
        assert 'clusters' in m
        assert isinstance(m['clusters'], list)

    def test_get_manifold_stats(self):
        """Stats include node count, cluster count, avg fitness."""
        idx = _MockSemanticIndex()
        evo = ThoughtEvolutionEngine(semantic_index=idx)
        for i in range(6):
            t = _make_thought(thought_id=f"ms{i}", content=f"Stats thought {i}")
            evo.ingest(t)
            evo._critic_scores[f"ms{i}"] = 0.5
        m = evo.get_manifold()
        stats = m['stats']
        assert stats['total_nodes'] == 6
        assert 'total_clusters' in stats
        assert 'avg_fitness' in stats

    def test_get_manifold_fitness_offsets_y(self):
        """High-fitness thoughts have higher Y coordinate."""
        idx = _MockSemanticIndex()
        evo = ThoughtEvolutionEngine(semantic_index=idx)
        for i in range(8):
            t = _make_thought(thought_id=f"mh{i}", content=f"Height thought {i} about topic")
            evo.ingest(t)
            evo._critic_scores[f"mh{i}"] = i * 0.1  # 0.0 to 0.7
        m = evo.get_manifold()
        # Find highest and lowest fitness nodes
        nodes_by_fitness = sorted(m['nodes'], key=lambda n: n['fitness'])
        low_y = nodes_by_fitness[0]['y']
        high_y = nodes_by_fitness[-1]['y']
        # High fitness should have higher y (with fitness offset)
        assert high_y > low_y
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestNeuralManifold -v`
Expected: FAIL — `ThoughtEvolutionEngine has no attribute 'get_manifold'`

**Step 3: Commit failing tests**

```bash
git add tests/test_brain_chat_quick.py
git commit -m "test: add failing tests for neural manifold get_manifold()"
```

---

## Task 3: Implement get_manifold() in ThoughtEvolutionEngine

**Files:**
- Modify: `core/brain_chat.py:2480` (after `get_graph()`, before `get_stats()`)

**Step 1: Add get_manifold() method**

Insert after `get_graph()` (line ~2506) and before `get_stats()` (line ~2510) in the `ThoughtEvolutionEngine` class:

```python
    def get_manifold(self) -> Dict[str, Any]:
        """Return 3D manifold projection with UMAP + DBSCAN clusters.

        Returns:
            Dict with nodes (3D coords), edges, clusters, stats
        """
        import numpy as np

        tids = list(self._embeddings.keys())
        # Filter to thoughts still in population
        tids = [t for t in tids if t in self._population]

        if not tids:
            return {'nodes': [], 'edges': [], 'clusters': [], 'stats': {
                'total_nodes': 0, 'total_clusters': 0, 'avg_fitness': 0.0,
            }}

        embeddings = np.array([self._embeddings[t] for t in tids])  # [N, 384]

        # ── UMAP 3D projection ──
        coords_3d = None
        if len(tids) >= 5:
            try:
                import umap
                reducer = umap.UMAP(
                    n_components=3,
                    n_neighbors=min(15, len(tids) - 1),
                    min_dist=0.1,
                    metric='cosine',
                    random_state=42,
                )
                coords_3d = reducer.fit_transform(embeddings)
            except Exception:
                pass

        if coords_3d is None:
            # Fallback: PCA-like projection for < 5 or UMAP failure
            if embeddings.shape[0] > 0:
                mean = embeddings.mean(axis=0)
                centered = embeddings - mean
                # Simple random projection
                rng = np.random.RandomState(42)
                proj = rng.randn(embeddings.shape[1], 3).astype(np.float32)
                proj, _ = np.linalg.qr(proj)
                coords_3d = centered @ proj
            else:
                coords_3d = np.zeros((0, 3))

        # ── Fitness Y-offset (attractor landscape) ──
        for i, tid in enumerate(tids):
            fitness = self._get_fitness(self._population[tid])
            if fitness >= 0:
                coords_3d[i, 1] += fitness * 2.0

        # ── DBSCAN clustering ──
        cluster_labels = np.full(len(tids), -1, dtype=int)
        if len(tids) >= 5:
            try:
                from sklearn.cluster import DBSCAN
                db = DBSCAN(eps=1.5, min_samples=3).fit(coords_3d)
                cluster_labels = db.labels_
            except Exception:
                pass

        # ── Build response ──
        nodes = []
        for i, tid in enumerate(tids):
            thought = self._population[tid]
            nodes.append({
                'id': tid,
                'x': round(float(coords_3d[i, 0]), 4),
                'y': round(float(coords_3d[i, 1]), 4),
                'z': round(float(coords_3d[i, 2]), 4),
                'fitness': round(self._get_fitness(thought), 3),
                'generation': thought.generation,
                'category': thought.category,
                'content': thought.content[:100],
                'cluster_id': int(cluster_labels[i]),
            })

        # Reuse edges from get_graph()
        graph = self.get_graph()

        # Build cluster summaries
        clusters = []
        unique_labels = set(cluster_labels)
        unique_labels.discard(-1)  # Remove noise label
        for label in sorted(unique_labels):
            mask = cluster_labels == label
            cluster_coords = coords_3d[mask]
            cluster_tids = [tids[i] for i in range(len(tids)) if mask[i]]
            fitness_vals = [
                self._get_fitness(self._population[t])
                for t in cluster_tids
                if self._get_fitness(self._population[t]) >= 0
            ]
            # Find dominant topic
            topics = [self._population[t].topic for t in cluster_tids if self._population[t].topic]
            dominant_topic = max(set(topics), key=topics.count) if topics else ""

            clusters.append({
                'id': int(label),
                'center_x': round(float(cluster_coords[:, 0].mean()), 4),
                'center_y': round(float(cluster_coords[:, 1].mean()), 4),
                'center_z': round(float(cluster_coords[:, 2].mean()), 4),
                'size': int(mask.sum()),
                'avg_fitness': round(sum(fitness_vals) / len(fitness_vals), 3) if fitness_vals else 0.0,
                'dominant_topic': dominant_topic,
            })

        # Stats
        all_fitness = [self._get_fitness(self._population[t]) for t in tids]
        scored_fitness = [f for f in all_fitness if f >= 0]
        avg_fitness = sum(scored_fitness) / len(scored_fitness) if scored_fitness else 0.0

        return {
            'nodes': nodes,
            'edges': graph['edges'],
            'clusters': clusters,
            'stats': {
                'total_nodes': len(nodes),
                'total_clusters': len(clusters),
                'avg_fitness': round(avg_fitness, 3),
                'max_generation': max((n['generation'] for n in nodes), default=0),
            },
        }
```

**Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestNeuralManifold -v`
Expected: 7/7 PASS

**Step 3: Run full test suite for regressions**

Run: `python -m pytest tests/test_brain_chat_quick.py -v --tb=short`
Expected: All pass (207 existing + 7 new = 214)

**Step 4: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: add get_manifold() with UMAP 3D projection and DBSCAN clustering"
```

---

## Task 4: Add API endpoint

**Files:**
- Modify: `web/routers/cortex.py` (add after thought-graph endpoint, before state endpoint)

**Step 1: Add GET /api/cortex/thought-manifold endpoint**

Insert after the `cortex_thought_graph` function (Route 4) and before Route 5 (`cortex_state`):

```python
# ===================================================================
# Route 5 — GET /api/cortex/thought-manifold
# ===================================================================

@router.get("/api/cortex/thought-manifold")
async def cortex_thought_manifold(request: Request) -> JSONResponse:
    """Return 3D UMAP manifold projection of thought embeddings.

    Returns ``{nodes, edges, clusters, stats}`` with 3D coordinates
    for Three.js visualization.
    """
    cte = request.app.state.continuous_thinking
    if cte is None:
        return JSONResponse({
            'nodes': [], 'edges': [], 'clusters': [],
            'stats': {'total_nodes': 0, 'total_clusters': 0, 'avg_fitness': 0.0},
        })

    evo = getattr(cte, '_evolution_engine', None)
    if evo is None:
        return JSONResponse({
            'nodes': [], 'edges': [], 'clusters': [],
            'stats': {'total_nodes': 0, 'total_clusters': 0, 'avg_fitness': 0.0},
        })

    try:
        manifold = evo.get_manifold()
        return JSONResponse(manifold)
    except Exception as exc:
        return JSONResponse(
            {"error": f"manifold projection failed: {exc}"},
            status_code=500,
        )
```

Update the Route 5 comment for the existing state endpoint to Route 6.

**Step 2: Verify endpoint manually**

Run: `curl http://localhost:5003/api/cortex/thought-manifold 2>/dev/null | python -m json.tool | head -5`
Expected: JSON with nodes/edges/clusters/stats keys

**Step 3: Commit**

```bash
git add web/routers/cortex.py
git commit -m "feat: add GET /api/cortex/thought-manifold endpoint"
```

---

## Task 5: Add Manifold tab and Three.js canvas to dashboard

**Files:**
- Modify: `web/templates/moltbook_dashboard.html`

This is the largest task. Three changes: tab button, tab content div, and Three.js/OrbitControls scripts.

**Step 1: Add tab button**

In the `.tab-bar` section (line ~490), after the Debug tab button, add:

```html
        <button class="tab-btn" onclick="switchTab('manifold')">Manifold</button>
```

**Step 2: Add tab content div**

After the last `tab-content` div (before the closing `</div>` of the main content area), add:

```html
      <!-- Tab: Neural Manifold (3D) -->
      <div class="tab-content" id="tab-manifold">
        <div id="manifold-container" style="width:100%;height:500px;background:#0d1117;border-radius:10px;position:relative;overflow:hidden;">
          <canvas id="manifold-canvas"></canvas>
          <div id="manifold-tooltip" style="display:none;position:absolute;background:rgba(0,0,0,0.85);color:#e6e6e6;padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;max-width:250px;z-index:10;"></div>
          <div id="manifold-stats" style="position:absolute;bottom:8px;left:8px;font-size:11px;color:#888;"></div>
        </div>
      </div>
```

**Step 3: Add Three.js and OrbitControls CDN scripts**

Before the closing `</body>` tag, add:

```html
<!-- Three.js for Neural Manifold -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
```

**Step 4: Add manifold viewer JavaScript**

After the Three.js script tags, add the inline JavaScript for the manifold viewer (see Task 6 for the full code).

**Step 5: Commit**

```bash
git add web/templates/moltbook_dashboard.html
git commit -m "feat: add Manifold tab with Three.js 3D canvas in Moltbook dashboard"
```

---

## Task 6: Implement Three.js manifold renderer

**Files:**
- Modify: `web/templates/moltbook_dashboard.html` (inline JS after Three.js CDN)

**Step 1: Add the full manifold viewer script**

Add this `<script>` block after the OrbitControls CDN script:

```javascript
<script>
// ── Neural Manifold 3D Viewer ──────────────────
let mScene, mCamera, mRenderer, mControls;
let mPoints = null, mLines = null;
let mInitialized = false;
let mRaycaster, mMouse;
let manifoldData = null;

function initManifold() {
  if (mInitialized) return;
  const container = document.getElementById('manifold-container');
  const canvas = document.getElementById('manifold-canvas');
  if (!container || !canvas || typeof THREE === 'undefined') return;

  const w = container.clientWidth, h = container.clientHeight;

  mScene = new THREE.Scene();
  mScene.background = new THREE.Color(0x0d1117);

  mCamera = new THREE.PerspectiveCamera(60, w / h, 0.1, 500);
  mCamera.position.set(5, 5, 8);

  mRenderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
  mRenderer.setSize(w, h);
  mRenderer.setPixelRatio(window.devicePixelRatio);

  mControls = new THREE.OrbitControls(mCamera, mRenderer.domElement);
  mControls.enableDamping = true;
  mControls.dampingFactor = 0.08;

  // Lights
  mScene.add(new THREE.AmbientLight(0x404040, 0.5));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(5, 10, 5);
  mScene.add(dirLight);

  // Grid helper
  const grid = new THREE.GridHelper(20, 20, 0x222244, 0x111133);
  grid.position.y = -2;
  mScene.add(grid);

  // Raycaster for hover
  mRaycaster = new THREE.Raycaster();
  mRaycaster.params.Points.threshold = 0.3;
  mMouse = new THREE.Vector2();

  canvas.addEventListener('mousemove', onManifoldMouseMove);

  mInitialized = true;
  animateManifold();
}

function animateManifold() {
  if (!mInitialized) return;
  requestAnimationFrame(animateManifold);
  mControls.update();
  mRenderer.render(mScene, mCamera);
}

function genColor(generation) {
  // blue(gen0) -> cyan(gen1) -> green(gen2) -> yellow(gen3) -> orange(gen4) -> red(gen5+)
  const t = Math.min(generation / 5, 1);
  const r = t;
  const g = Math.max(0, 1 - Math.abs(t - 0.5) * 2);
  const b = 1 - t;
  return [r, g, b];
}

function renderManifold(data) {
  if (!mScene) return;
  manifoldData = data;

  // Remove old geometry
  if (mPoints) { mScene.remove(mPoints); mPoints.geometry.dispose(); }
  if (mLines) { mScene.remove(mLines); mLines.geometry.dispose(); }

  const nodes = data.nodes || [];
  if (nodes.length === 0) return;

  // ── Points ──
  const positions = new Float32Array(nodes.length * 3);
  const colors = new Float32Array(nodes.length * 3);
  const sizes = new Float32Array(nodes.length);

  nodes.forEach((n, i) => {
    positions[i*3]   = n.x;
    positions[i*3+1] = n.y;
    positions[i*3+2] = n.z;
    const [r, g, b] = genColor(n.generation);
    colors[i*3] = r; colors[i*3+1] = g; colors[i*3+2] = b;
    sizes[i] = (n.fitness >= 0 ? 0.15 + n.fitness * 0.25 : 0.12);
  });

  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  const mat = new THREE.PointsMaterial({
    size: 0.3, vertexColors: true, transparent: true, opacity: 0.9,
    sizeAttenuation: true,
  });
  mPoints = new THREE.Points(geom, mat);
  mScene.add(mPoints);

  // ── Edges ──
  const edges = data.edges || [];
  if (edges.length > 0) {
    const nodeMap = {};
    nodes.forEach((n, i) => { nodeMap[n.id] = i; });
    const linePositions = [];
    const lineColors = [];
    edges.forEach(e => {
      const si = nodeMap[e.source], ti = nodeMap[e.target];
      if (si === undefined || ti === undefined) return;
      const s = nodes[si], t = nodes[ti];
      linePositions.push(s.x, s.y, s.z, t.x, t.y, t.z);
      if (e.type === 'parent') {
        lineColors.push(0.2,0.8,0.4, 0.2,0.8,0.4); // green
      } else {
        lineColors.push(0.3,0.3,0.5, 0.3,0.3,0.5); // dim blue
      }
    });
    const lineGeom = new THREE.BufferGeometry();
    lineGeom.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
    lineGeom.setAttribute('color', new THREE.Float32BufferAttribute(lineColors, 3));
    const lineMat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.4 });
    mLines = new THREE.LineSegments(lineGeom, lineMat);
    mScene.add(mLines);
  }

  // ── Stats overlay ──
  const statsEl = document.getElementById('manifold-stats');
  if (statsEl && data.stats) {
    const s = data.stats;
    statsEl.textContent = `${s.total_nodes} thoughts | ${s.total_clusters} clusters | avg fitness: ${s.avg_fitness} | max gen: ${s.max_generation || 0}`;
  }
}

function onManifoldMouseMove(event) {
  if (!mPoints || !manifoldData) return;
  const rect = mRenderer.domElement.getBoundingClientRect();
  mMouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  mMouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  mRaycaster.setFromCamera(mMouse, mCamera);
  const intersects = mRaycaster.intersectObject(mPoints);
  const tooltip = document.getElementById('manifold-tooltip');
  if (intersects.length > 0) {
    const idx = intersects[0].index;
    const node = manifoldData.nodes[idx];
    if (node) {
      tooltip.style.display = 'block';
      tooltip.style.left = (event.clientX - mRenderer.domElement.getBoundingClientRect().left + 12) + 'px';
      tooltip.style.top = (event.clientY - mRenderer.domElement.getBoundingClientRect().top - 20) + 'px';
      tooltip.innerHTML = `<b>[${node.category}]</b> gen ${node.generation}<br>${esc(node.content)}<br>fitness: ${node.fitness}`;
    }
  } else {
    tooltip.style.display = 'none';
  }
}

async function refreshManifold() {
  try {
    const resp = await fetch('/api/cortex/thought-manifold');
    const data = await resp.json();
    if (!mInitialized) initManifold();
    renderManifold(data);
  } catch(e) {
    console.log('manifold refresh error:', e.message);
  }
}

// Auto-refresh manifold every 10s when tab is active
setInterval(() => {
  const tab = document.getElementById('tab-manifold');
  if (tab && tab.classList.contains('active')) {
    refreshManifold();
  }
}, 10000);

// Init when manifold tab is first clicked
const origSwitchTab = switchTab;
switchTab = function(name) {
  origSwitchTab(name);
  if (name === 'manifold') {
    refreshManifold();
  }
};
</script>
```

**Step 2: Verify visually**

1. Start the brain server: `python -m web.brain_server`
2. Open `http://localhost:5003/ui/moltbook`
3. Click the "Manifold" tab
4. Wait 10+ seconds for thoughts to accumulate
5. Should see 3D point cloud with orbit controls

**Step 3: Commit**

```bash
git add web/templates/moltbook_dashboard.html
git commit -m "feat: implement Three.js neural manifold viewer with hover tooltips"
```

---

## Task 7: Run full test suite + final commit

**Step 1: Run all tests**

Run: `python -m pytest tests/test_brain_chat_quick.py -v --tb=short`
Expected: All pass (214+ tests)

**Step 2: Smoke test**

Run: `python -c "from core.brain_chat import ThoughtEvolutionEngine; e = ThoughtEvolutionEngine(); print(e.get_manifold()['stats'])"`
Expected: `{'total_nodes': 0, 'total_clusters': 0, 'avg_fitness': 0.0}`

**Step 3: Final commit if any loose changes**

```bash
git add -A
git commit -m "chore: neural manifold implementation complete"
```
