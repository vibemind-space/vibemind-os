
"""
function_map.py

Defines all the callable functions and a mapping from
string names to these functions.
"""

def greet(name: str, message: str):
    """Return a greeting string."""
    return f"{message}, {name}!"

def add(a: int, b: int):
    """Return the sum of two integers."""
    return a + b

def get_account_balance(user_id: str):
    """Return a mock account balance for the given user_id."""
    return f"User {user_id} has a balance of $123.45."

# A configurable mapping from function identifiers to actual Python functions
FUNCTIONS_MAP = {
    "greet": greet,
    "add": add,
    "get_account_balance": get_account_balance
}
