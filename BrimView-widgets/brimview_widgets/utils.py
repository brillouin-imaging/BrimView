import panel as pn
import asyncio
from functools import wraps
import weakref

import numpy as np

from .logging import logger

def only_on_change(*param_names):
    """
    Decorator to avoid re-running a @param.depends-rendered method unless specific parameters have changed.

    This is especially useful for expensive methods that generate plots or views used in Panel,
    and are decorated with @param.depends(..., watch=False). Panel expects these functions to
    always return something (usually a plot), even if the parameters haven't changed.

    Behavior:
    - If any of the specified `param_names` have changed since the last call, the wrapped function is executed.
    - If none of them have changed:
        - If the function was previously called, the last returned result is returned again.
        - If the function has never been called before, returns `None`.

    Limitations:
    - Parameters must be comparable using `!=`.
    - Does not handle in-place mutation detection (e.g. lists or dicts mutated without reassignment).
    - One cache is maintained per instance and per function.

    Example usage:
        @param.depends("x", "y", watch=False)
        @only_on_change("x", "y")
        def my_plot(self):
            return hv.Image(...)  # expensive plot generation
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
             # get the state dictionary of the current instance
            curr_state = wrapper._state_dict.get(self, {})
     
            dependencies_value_attr = "dependencies_value"
            dependencies_changed_attr = "dependencies_changed"
            last_return_value_attr = "last_return_value"

            # Get the current values of the dependencies
            deps_vals = [getattr(self, dep) for dep in param_names]
            if not dependencies_value_attr in curr_state:
                # First call, consider dependencies as changed
                # N.B. This will also create the attribute "dependencies_changed" on the first call to the wrapper
                curr_state[dependencies_changed_attr] = True
            else:
                # Check if any of the dependencies have changed only if they haven't already been marked as changed
                if not curr_state[dependencies_changed_attr]:
                    curr_state[dependencies_changed_attr] = any(
                        deps_vals[i] != curr_state[dependencies_value_attr][i] for i in range(len(param_names))
                    )
            # Store current dependencies values for next comparison
            curr_state[dependencies_value_attr] = deps_vals
            
            if not curr_state[dependencies_changed_attr]: # no change in dependencies
                if last_return_value_attr in curr_state:
                    logger.debug(f"[{func.__name__}] Skipping (no change), but returning previous value.")
                else:
                    logger.debug(f"[{func.__name__}] Skipping (no change), but no previous return value yet.")
            else:
                curr_state[last_return_value_attr] = func(self, *args, **kwargs)
                # we just called the function, so mark dependencies as unchanged for next time
                curr_state[dependencies_changed_attr] = False
            
            # update the state dictionary of the current instance
            wrapper._state_dict[self] = curr_state

            return curr_state.get(last_return_value_attr, None)
        # create a state dictionary for the wrapper function to store the state of each instance of the class where the decorated method is defined 
        if not hasattr(wrapper, "_state_dict"):
            wrapper._state_dict = weakref.WeakKeyDictionary()
        return wrapper
    return decorator

def catch_and_notify(duration=4000, notification_type="error", prefix=""):
    """
    Decorator to catch exceptions and show a Panel toast notification.

    Args:
        duration (int): Duration of the notification in ms.
        notification_type (str): One of 'info', 'success', 'warning', 'error'.
        prefix (str): Custom (HTML) text to prefix the error message.
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    msg = f"{prefix}{type(e).__name__}: {str(e)}"
                    getattr(pn.state.notifications, notification_type)(msg, duration=duration)
                    logger.error(f"Error in {func.__name__}: {msg}")
                    return None
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    msg = f"{prefix}{type(e).__name__}: {str(e)}"
                    getattr(pn.state.notifications, notification_type)(msg, duration=duration)
                    logger.error(f"Error in {func.__name__}: {msg}")
                    return None
            return sync_wrapper
    return decorator

def safe_get(container, *keys, default=None):
    """
    Safely get a nested value from dict-like containers.
    
    Example:
        safe_get(qts, "Width", peak.name, default=None)
    """
    try:
        value = container
        for key in keys:
            value = value[key]
        return value.value
    except Exception:
        return default
    
def points_in_polygon(points, polygon):
    """
    Check if points are inside a polygon using ray casting algorithm.
    
    Parameters
    ----------
    points : (N, 2) array
        Points to test as (x, y) coordinates
    polygon : (M, 2) array
        Polygon vertices as (x, y) coordinates
    
    Returns
    -------
    mask : (N,) bool array
        True for points inside the polygon
    """
    n = len(polygon)
    inside = np.zeros(len(points), dtype=bool)
    
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        
        # Check if point is within y bounds
        y_check = (points[:, 1] > min(p1y, p2y)) & (points[:, 1] <= max(p1y, p2y))
        
        # Check if point is to the left of the edge
        if p2y != p1y:  # Avoid division by zero
            x_intersect = (points[:, 1] - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
            inside ^= y_check & (points[:, 0] < x_intersect)
        
        p1x, p1y = p2x, p2y
    
    return inside