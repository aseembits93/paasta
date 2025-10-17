from paasta_tools.autoscaling.utils import get_autoscaling_component
from paasta_tools.autoscaling.utils import register_autoscaling_component
from paasta_tools.long_running_service_tools import (
    DEFAULT_UWSGI_AUTOSCALING_MOVING_AVERAGE_WINDOW,
)


FORECAST_POLICY_KEY = "forecast_policy"


def get_forecast_policy(name):
    """
    Returns a forecast policy matching the given name. Only used by decision policies that try to forecast load, like
    the proportional decision policy.
    """
    return get_autoscaling_component(name, FORECAST_POLICY_KEY)


@register_autoscaling_component("current", FORECAST_POLICY_KEY)
def current_value_forecast_policy(historical_load, **kwargs):
    """A prediction policy that assumes that the value any time in the future will be the same as the current value.

    :param historical_load: a list of (timestamp, value)s, where timestamp is a unix timestamp and value is load.
    """
    return historical_load[-1][1]


def window_historical_load(historical_load, window_begin, window_end):
    """Filter historical_load down to just the datapoints lying between times window_begin and window_end, inclusive."""
    filtered = []
    for timestamp, value in historical_load:
        if timestamp >= window_begin and timestamp <= window_end:
            filtered.append((timestamp, value))
    return filtered


def trailing_window_historical_load(historical_load, window_size):
    window_end, _ = historical_load[-1]
    window_begin = window_end - window_size

    index = len(historical_load) - 1
    while index >= 0 and historical_load[index][0] >= window_begin:
        index -= 1

    return historical_load[index + 1 :]


@register_autoscaling_component("moving_average", FORECAST_POLICY_KEY)
def moving_average_forecast_policy(
    historical_load,
    moving_average_window_seconds=DEFAULT_UWSGI_AUTOSCALING_MOVING_AVERAGE_WINDOW,
    **kwargs,
):
    """Does a simple average of all historical load data points within the moving average window. Weights all data
    points within the window equally."""

    windowed_data = trailing_window_historical_load(
        historical_load, moving_average_window_seconds
    )
    windowed_values = [value for timestamp, value in windowed_data]
    return sum(windowed_values) / len(windowed_values)


@register_autoscaling_component("linreg", FORECAST_POLICY_KEY)
def linreg_forecast_policy(
    historical_load,
    linreg_window_seconds,
    linreg_extrapolation_seconds,
    linreg_default_slope=0,
    **kwargs,
):
    """Does a linear regression on the load data within the last linreg_window_seconds. For every time delta in
    linreg_extrapolation_seconds, forecasts the value at that time delta from now, and returns the maximum of these
    predicted values. (With linear extrapolation, it doesn't make sense to forecast at more than two points, as the max
    load will always be at the first or last time delta.)

    :param linreg_window_seconds: Consider all data from this many seconds ago until now.
    :param linreg_extrapolation_seconds: A list of floats representing a number of seconds in the future at which to
                                         predict the load. The highest prediction will be returned.
    :param linreg_default_slope: If there is only one data point within the window, the equation for slope is undefined,
                                 so we use this value (expressed in load/second) for prediction instead. Default is
                                 0.

    """

    window = trailing_window_historical_load(historical_load, linreg_window_seconds)

    n = len(window)
    sum_time = 0
    sum_load = 0
    sum_time_sq = 0
    sum_time_load = 0
    for timestamp, load in window:
        sum_time += timestamp
        sum_load += load
        sum_time_sq += timestamp * timestamp
        sum_time_load += timestamp * load

    mean_time = sum_time / n
    mean_load = sum_load / n

    if len(window) > 1:
        numerator = sum_time_load - (sum_time * sum_load) / n
        denominator = sum_time_sq - (sum_time * sum_time) / n
        slope = numerator / denominator
    else:
        slope = linreg_default_slope

    intercept = mean_load - slope * mean_time

    def predict(timestamp):
        return slope * timestamp + intercept

    if isinstance(linreg_extrapolation_seconds, (int, float)):
        linreg_extrapolation_seconds = [linreg_extrapolation_seconds]

    now, _ = historical_load[-1]
    forecasted_values = [predict(now + delta) for delta in linreg_extrapolation_seconds]
    return max(forecasted_values)
