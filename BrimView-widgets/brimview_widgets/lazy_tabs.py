import param
import panel as pn
import functools
import weakref

class ActiveTabWatcher(param.Parameterized):
    """
    Watches a specific tab in a `pn.Tabs` widget and exposes its active state
    as a reactive `param.Boolean` parameter.

    The `active` parameter is `True` when the watched tab is currently selected
    and `False` otherwise. It updates automatically whenever the active tab changes.
    """

    # This parameter will be True when the watched tab is active, False otherwise
    active = param.Boolean(default=False)

    def __init__(self, tabs: pn.Tabs, index_of_tab_to_watch: int, **params):
        """
        Initialize the watcher and bind it to the given tab.

        Parameters
        ----------
        tabs : pn.Tabs
            The `Tabs` widget to monitor.
        index_of_tab_to_watch : int
            Zero-based index of the tab whose active state should be tracked.
        **params
            Additional keyword arguments forwarded to `param.Parameterized`.
        """
        super().__init__(**params)
        # define a parameter that will be True when the watched tab is active, False otherwise
        self.active = (tabs.active == index_of_tab_to_watch)
        # define a callback to update the parameter when the active tab changes
        def _update_tab_active_param(active):
            self.active = (active == index_of_tab_to_watch)
        # bind the callback to the Tabs active parameter
        param.bind(_update_tab_active_param, tabs.param.active, watch=True)

def depends_when_active(*dependencies, watch: bool = False):
    """A custom version of `param.depends` that only triggers the decorated function when the "active" parameter is (or becomes) True.
    This is useful for avoiding expensive computations when a certain tab or section of the UI is not active.
    The "active" parameter is expected to be a `param.Boolean` that is present in the class where the decorated method is defined.
    """
    def decorator(func):
        @param.depends(*dependencies, "active", watch=watch)
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # get the state dictionary of the current instance
            curr_state = wrapper._state_dict.get(self, {})
     
            dependencies_value_attr = "dependencies_value"
            dependencies_changed_attr = "dependencies_changed"
            last_return_value_attr = "last_return_value"

            # Get the current values of the dependencies
            deps_vals = [getattr(self, dep) for dep in dependencies]
            if not dependencies_value_attr in curr_state:
                # First call, consider dependencies as changed
                # N.B. This will also create the attribute "dependencies_changed" on the first call to the wrapper
                curr_state[dependencies_changed_attr] = True
            else:
                # Check if any of the dependencies have changed only if they haven't already been marked as changed
                if not curr_state[dependencies_changed_attr]:
                    curr_state[dependencies_changed_attr] = any(
                        deps_vals[i] != curr_state[dependencies_value_attr][i] for i in range(len(dependencies))
                    )
            # Store current dependencies values for next comparison
            curr_state[dependencies_value_attr] = deps_vals
            # Only call the original function if the "active" parameter is True and dependencies have changed
            if self.active and curr_state[dependencies_changed_attr]:
                curr_state[dependencies_changed_attr] = False
                # store the last computed value so that it can be returned when the new value of the function is not computed
                curr_state[last_return_value_attr] = func(self, *args, **kwargs)
            # update the state dictionary of the current instance
            wrapper._state_dict[self] = curr_state
            # Return the last computed value even if "active" is False or dependencies haven't changed
            return curr_state.get(last_return_value_attr, None)
        # create a state dictionary for the wrapper function to store the state of each instance of the class where the decorated method is defined 
        if not hasattr(wrapper, "_state_dict"):
            wrapper._state_dict = weakref.WeakKeyDictionary()
        return wrapper
    return decorator