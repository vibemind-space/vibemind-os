"""
Klotski Puzzle State Representation

Represents the puzzle board state with brain module pieces.
Each piece corresponds to a brain module from the connectome graph.

Based on: Klotski_NeuroLayout.json
"""

import json
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from copy import deepcopy


@dataclass
class PuzzlePiece:
    """Represents a single puzzle piece (brain module)"""
    piece_id: str  # G, V, A, S, L, D, C, I, M, O
    x: int         # Column position (0-3)
    y: int         # Row position (0-4)
    w: int         # Width (1 or 2)
    h: int         # Height (1 or 2)
    module: str    # Brain module name (DMN, VIS, AUD, etc.)
    brodmann_areas: str
    math_type: str

    def get_occupied_cells(self) -> Set[Tuple[int, int]]:
        """Get all cells occupied by this piece"""
        cells = set()
        for dy in range(self.h):
            for dx in range(self.w):
                cells.add((self.x + dx, self.y + dy))
        return cells

    def can_move_to(self, new_x: int, new_y: int, board_width: int, board_height: int,
                    occupied_cells: Set[Tuple[int, int]]) -> bool:
        """Check if piece can move to new position"""
        # Check boundaries
        if new_x < 0 or new_y < 0:
            return False
        if new_x + self.w > board_width or new_y + self.h > board_height:
            return False

        # Check collision with other pieces
        new_cells = set()
        for dy in range(self.h):
            for dx in range(self.w):
                cell = (new_x + dx, new_y + dy)
                new_cells.add(cell)
                # If cell is occupied and not by this piece, collision
                if cell in occupied_cells and cell not in self.get_occupied_cells():
                    return False

        return True

    def __repr__(self):
        return f"Piece({self.piece_id}, pos=({self.x},{self.y}), size={self.w}x{self.h}, module={self.module})"


class PuzzleState:
    """
    Represents the complete puzzle state

    Board layout (4x5):
    y/x  0 1 2 3
    0    V G G A
    1    V G G A
    2    S D D L
    3    S C I L
    4    M O . .

    Exit: bottom (y=4) at positions x=1,2
    """

    def __init__(self, layout_file: str = None, pieces: List[PuzzlePiece] = None):
        """
        Initialize puzzle state from layout file or piece list

        Args:
            layout_file: Path to Klotski_NeuroLayout.json
            pieces: List of PuzzlePiece objects (alternative to layout_file)
        """
        if layout_file:
            self._load_from_file(layout_file)
        elif pieces:
            self.pieces = {p.piece_id: p for p in pieces}
            self.board_width = 4
            self.board_height = 5
            self.exit_cells = [(1, 4), (2, 4)]
        else:
            raise ValueError("Must provide either layout_file or pieces")

        self._update_occupied_cells()

    def _load_from_file(self, filepath: str):
        """Load puzzle layout from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Board configuration
        self.board_width = data['board']['width']
        self.board_height = data['board']['height']
        self.exit_cells = [tuple(cell) for cell in data['board']['exit']]

        # Create pieces
        self.pieces = {}
        for piece_data in data['pieces']:
            piece_id = piece_data['id']
            meta = data['meta']['mapping'][piece_id]

            piece = PuzzlePiece(
                piece_id=piece_id,
                x=piece_data['x'],
                y=piece_data['y'],
                w=piece_data['w'],
                h=piece_data['h'],
                module=meta['module'],
                brodmann_areas=meta['ba'],
                math_type=meta['math']
            )
            self.pieces[piece_id] = piece

    def _update_occupied_cells(self):
        """Update the set of all occupied cells"""
        self.occupied_cells = set()
        for piece in self.pieces.values():
            self.occupied_cells.update(piece.get_occupied_cells())

    def get_empty_cells(self) -> Set[Tuple[int, int]]:
        """Get all empty cells on the board"""
        all_cells = {(x, y) for x in range(self.board_width)
                     for y in range(self.board_height)}
        return all_cells - self.occupied_cells

    def get_piece_at(self, x: int, y: int) -> Optional[PuzzlePiece]:
        """Get piece at specific cell position"""
        for piece in self.pieces.values():
            if (x, y) in piece.get_occupied_cells():
                return piece
        return None

    def get_valid_moves(self, piece_id: str) -> List[Tuple[int, int, str]]:
        """
        Get all valid moves for a piece

        Returns:
            List of (new_x, new_y, direction) tuples
        """
        if piece_id not in self.pieces:
            return []

        piece = self.pieces[piece_id]
        moves = []

        # Try four directions: up, down, left, right
        directions = [
            (0, -1, "up"),
            (0, 1, "down"),
            (-1, 0, "left"),
            (1, 0, "right"),
        ]

        for dx, dy, direction in directions:
            new_x = piece.x + dx
            new_y = piece.y + dy

            # Create temporary occupied cells excluding current piece
            temp_occupied = self.occupied_cells - piece.get_occupied_cells()

            if piece.can_move_to(new_x, new_y, self.board_width, self.board_height, temp_occupied):
                moves.append((new_x, new_y, direction))

        return moves

    def move_piece(self, piece_id: str, new_x: int, new_y: int) -> bool:
        """
        Move a piece to new position

        Returns:
            True if move was successful, False otherwise
        """
        if piece_id not in self.pieces:
            return False

        piece = self.pieces[piece_id]

        # Create temporary occupied cells excluding current piece
        temp_occupied = self.occupied_cells - piece.get_occupied_cells()

        if not piece.can_move_to(new_x, new_y, self.board_width, self.board_height, temp_occupied):
            return False

        # Execute move
        piece.x = new_x
        piece.y = new_y
        self._update_occupied_cells()

        return True

    def is_solved(self) -> bool:
        """
        Check if puzzle is solved

        Puzzle is solved when DMN (piece 'G', 2×2) reaches the exit
        Exit is at bottom (y=4) with x=1,2
        """
        if 'G' not in self.pieces:
            return False

        dmn_piece = self.pieces['G']  # DMN is the 2×2 piece 'G'

        # DMN should be at position (1, 3) to occupy cells (1,3), (2,3), (1,4), (2,4)
        # This places the bottom half at the exit
        return dmn_piece.x == 1 and dmn_piece.y == 3

    def get_board_string(self) -> str:
        """
        Get string representation of board state

        Returns:
            String where each character represents a cell (piece ID or '.')
        """
        board = [['.' for _ in range(self.board_width)]
                 for _ in range(self.board_height)]

        for piece in self.pieces.values():
            for x, y in piece.get_occupied_cells():
                board[y][x] = piece.piece_id

        return '\n'.join(''.join(row) for row in board)

    def get_state_hash(self) -> str:
        """
        Get unique hash for this state

        Returns:
            String hash representing piece positions
        """
        # Create sorted list of (piece_id, x, y) tuples
        positions = sorted(
            [(p.piece_id, p.x, p.y) for p in self.pieces.values()]
        )
        return '|'.join(f"{pid}:{x},{y}" for pid, x, y in positions)

    def clone(self) -> 'PuzzleState':
        """Create a deep copy of this state"""
        pieces_copy = [deepcopy(p) for p in self.pieces.values()]
        return PuzzleState(pieces=pieces_copy)

    def __repr__(self):
        return f"PuzzleState(pieces={len(self.pieces)}, empty={len(self.get_empty_cells())}, solved={self.is_solved()})"

    def __str__(self):
        return self.get_board_string()


if __name__ == "__main__":
    # Test puzzle state
    import os

    # Try to load from Downloads folder
    layout_path = r"C:\Users\User\Downloads\Klotski_NeuroLayout.json"

    if os.path.exists(layout_path):
        print("Loading puzzle from:", layout_path)
        puzzle = PuzzleState(layout_file=layout_path)

        print("\nPuzzle State:")
        print(puzzle)

        print("\nBoard visualization:")
        print(puzzle.get_board_string())

        print("\nPiece information:")
        for piece_id, piece in sorted(puzzle.pieces.items()):
            print(f"  {piece}")

        print("\nEmpty cells:", puzzle.get_empty_cells())

        print("\nValid moves for DLPFC (D):")
        moves = puzzle.get_valid_moves('D')
        for new_x, new_y, direction in moves:
            print(f"  {direction}: to ({new_x}, {new_y})")

        print("\nIs solved?", puzzle.is_solved())

        print("\nState hash:", puzzle.get_state_hash())

        # Test a move
        print("\nTesting move: Moving piece 'D' down...")
        if puzzle.move_piece('D', 1, 3):
            print("Move successful!")
            print(puzzle.get_board_string())
        else:
            print("Move failed!")
    else:
        print(f"Layout file not found at: {layout_path}")
