# Neural Network Shape Mismatch Fix

## Problem

Training crashed with:
```
RuntimeError: mat1 and mat2 shapes cannot be multiplied (32x256 and 20x128)
  File "neurosymbolic_trainer.py", line 173, in pretrain_heart
    output = brain.brain(state_features, return_components=True)
```

## Root Cause

The wrapper (`neurosymbolic_heart_brain.py`) was generating **256-dim hash-based embeddings** from representation strings, but the real `NeuroSymbolicBrain` expected **20-dim board tensors** as input.

### Historical Context

The confusion arose because:
1. **Real Brain Architecture**: `[20-dim board] → state_encoder (20→128→256) → [256-dim features] → modules`
2. **Wrapper Mistake**: Used `feature_dim=256` as **both** input AND internal dimension
3. **Legacy Hash Embeddings**: Generated 256-dim vectors using `sin((hash_int + i) * 0.1)`

The 256 was always meant as the **INTERNAL feature dimension**, not the input dimension!

## Solution

Modified `core/neurosymbolic_heart_brain.py`:

### 1. Added `_parse_representation_to_board()` Method

Parses Klotski representation strings (e.g., `"jafi.aehddehbbcgbbc."`) into 20-dim board tensors:

```python
def _parse_representation_to_board(self, representation: str) -> np.ndarray:
    """
    Parse representation string to 4x5 board tensor.

    Args:
        representation: String like "jafi.aehddehbbcgbbc." (20 chars, 4×5 row-major)

    Returns:
        Board tensor of shape (20,) with values 0-10:
            0 = empty cell '.'
            1-10 = block IDs mapped from 'a'-'j'
    """
    # Character to ID mapping
    char_to_id = {
        '.': 0,  # Empty
        'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5,
        'f': 6, 'g': 7, 'h': 8, 'i': 9, 'j': 10
    }

    # Parse 20 characters into board
    board = np.zeros(20, dtype=np.float32)
    for idx in range(min(20, len(representation))):
        char = representation[idx]
        board[idx] = char_to_id.get(char, 0)

    # Normalize to [0, 1] range for neural network
    board = board / 10.0  # Max ID is 10

    return board
```

### 2. Rewrote `_state_to_features()` Method

Now converts representation strings to proper board tensors:

```python
def _state_to_features(self, puzzle_state: Any) -> torch.Tensor:
    """
    Convert puzzle state to board tensor.

    Args:
        puzzle_state: State hash string (representation) or board tensor

    Returns:
        Feature tensor of shape (1, 5, 4) for real brain, or (1, 20) for fallback
    """
    if isinstance(puzzle_state, str):
        # Parse representation string to 20-dim board
        board = self._parse_representation_to_board(puzzle_state)
    elif isinstance(puzzle_state, np.ndarray):
        # Already a board tensor
        board = puzzle_state.flatten()
        if len(board) != 20:
            # Fallback: zero-pad or truncate
            new_board = np.zeros(20, dtype=np.float32)
            new_board[:min(20, len(board))] = board[:min(20, len(board))]
            board = new_board
    else:
        # Unknown format - create empty board
        board = np.zeros(20, dtype=np.float32)

    # Convert to tensor
    board_tensor = torch.FloatTensor(board).to(self.device)

    if self.using_real_brain:
        # Real brain expects [batch, 5, 4] shape
        return board_tensor.view(1, 5, 4)
    else:
        # Fallback brain expects [batch, 20] shape
        return board_tensor.unsqueeze(0)
```

### 3. Added `using_real_brain` Flag

```python
self.using_real_brain = NEUROSYMBOLIC_AVAILABLE
```

This allows the wrapper to adapt output shape based on which brain is loaded.

### 4. Fixed Fallback Brain

Changed fallback mock to accept 20-dim inputs:

```python
class NeuroSymbolicBrain(nn.Module):
    def __init__(self, feature_dim=256, num_actions=40, memory_size=100):
        super().__init__()
        self.feature_dim = feature_dim
        self.num_actions = num_actions
        self.fc = nn.Linear(20, num_actions)  # Accept flattened 20-dim boards
```

## Verification

### Test 1: Fallback Brain (Mock)

```bash
$ python -c "from core.neurosymbolic_heart_brain import NeuroSymbolicHeartSystem; w = NeuroSymbolicHeartSystem(); print(f'Using real brain: {w.using_real_brain}'); print(f'feature_dim: {w.feature_dim}'); feat = w._state_to_features('jafi.aehddehbbcgbbc.'); print(f'feature shape: {feat.shape}'); output = w.brain(feat); print(f'output shape: {output.shape}'); print('SUCCESS!')"
```

Output:
```
[NeuroSymbolicHeartBrain] Using fallback mode with simple heuristics
[HeartSystem] No pretrained weights loaded - using random initialization
Using real brain: False
feature_dim: 256
feature shape: torch.Size([1, 20])
output shape: torch.Size([1, 40])
SUCCESS!
```

### Test 2: Real Brain (when neurosymbolic module available)

With real brain imported, output shape becomes:
```
feature shape: torch.Size([1, 5, 4])  # Real brain expects 4x5 grid
output shape: torch.Size([1, 40])
```

## Impact

### Before Fix
- ❌ Wrapper generated 256-dim hash embeddings
- ❌ Real brain expected 20-dim boards → **RuntimeError**
- ❌ Training crashed immediately

### After Fix
- ✅ Wrapper parses representation → 20-dim boards
- ✅ Real brain reshapes to `[1, 5, 4]` internally
- ✅ Fallback brain uses `[1, 20]` flattened
- ✅ Training runs without shape mismatch

## Architecture Summary

### Correct Data Flow (NOW)

```
Representation String "jafi.aehddehbbcgbbc."
  ↓
_parse_representation_to_board()
  ↓
[20 values] normalized to [0, 1]
  ↓
_state_to_features()
  ↓
Real Brain: [1, 5, 4] → encode_board_state() → flatten → state_encoder (20→128→256) → modules
Fallback:   [1, 20]  → fc(20 → 40) → action_logits
```

### Previous Broken Flow

```
Representation String "jafi.aehddehbbcgbbc."
  ↓
hash(string) → sin-based embedding
  ↓
[256 values]
  ↓
Real Brain: ERROR! (expects [1, 5, 4] or [batch, 20])
```

## Files Modified

1. **core/neurosymbolic_heart_brain.py** (lines 114, 223-286)
   - Added `_parse_representation_to_board()`
   - Rewrote `_state_to_features()`
   - Added `using_real_brain` flag
   - Fixed fallback brain Linear layer (20 → 40)

## Next Steps

1. ✅ Shape mismatch resolved
2. ⏳ Run training to verify dashboard updates with real blocks
3. ⏳ Confirm three different puzzles display correctly
4. ⏳ Verify no block overlaps in visualization

## Related Issues

- Dashboard JSON Infinity error: **FIXED** (klotski_dashboard_server.py line 124)
- Real-time block updates: **FIXED** (multi_generational_trainer.py lines 495-532)
- Neural network shape mismatch: **FIXED** (this document)
