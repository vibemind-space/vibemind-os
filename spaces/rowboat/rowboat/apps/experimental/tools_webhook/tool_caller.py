# tool_caller.py

import inspect
import logging

logger = logging.getLogger(__name__)

def call_tool(function_name: str, parameters: dict, functions_map: dict):
    """
    1) Lookup a function in functions_map by name.
    2) Validate parameters against the function signature.
    3) Call the function with converted parameters.
    4) Return the result or raise an Exception on error.
    """

    logger.debug("call_tool invoked with function_name=%s, parameters=%s", function_name, parameters)

    # 1) Check if function exists
    if function_name not in functions_map:
        error_msg = f"Function '{function_name}' not found."
        logger.error(error_msg)
        raise ValueError(error_msg)

    func = functions_map[function_name]
    signature = inspect.signature(func)

    # 2) Identify required parameters
    required_params = [
        pname for pname, p in signature.parameters.items()
        if p.default == inspect.Parameter.empty
    ]

    # Check required params
    for rp in required_params:
        if rp not in parameters:
            error_msg = f"Missing required parameter: {rp}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # Check unexpected params
    valid_param_names = signature.parameters.keys()
    for p in parameters.keys():
        if p not in valid_param_names:
            error_msg = f"Unexpected parameter: {p}"
            logger.error(error_msg)
            raise ValueError(error_msg)

    # 3) Convert types based on annotations (if any)
    converted_params = {}
    for param_name, param_value in parameters.items():
        param_obj = signature.parameters[param_name]
        if param_obj.annotation != inspect.Parameter.empty:
            try:
                converted_params[param_name] = param_obj.annotation(param_value)
            except (ValueError, TypeError) as e:
                error_msg = f"Parameter '{param_name}' must be of type {param_obj.annotation.__name__}: {e}"
                logger.error(error_msg)
                raise ValueError(error_msg)
        else:
            converted_params[param_name] = param_value

    # 4) Invoke the function
    try:
        result = func(**converted_params)
        logger.debug("Function '%s' returned: %s", function_name, result)
        return result
    except Exception as e:
        logger.exception("Unexpected error calling '%s'", function_name)  # logs stack trace
        raise
