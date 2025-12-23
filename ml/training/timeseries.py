"""
SARIMAX model training script for time-series forecasting
"""
import pandas as pd
import numpy as np
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.seasonal import seasonal_decompose
import pickle
from pathlib import Path
from typing import Optional
import warnings
warnings.filterwarnings('ignore')


def prepare_timeseries_data(
    data: pd.DataFrame,
    time_col: str = 'event_time',
    value_col: str = 'risk_score'
) -> pd.Series:
    """
    Prepare time series data for SARIMAX model.
    
    Args:
        data: DataFrame with time and value columns
        time_col: Name of time column
        value_col: Name of value column
    
    Returns:
        Time series as pandas Series with DatetimeIndex
    """
    df = data.copy()
    df[time_col] = pd.to_datetime(df[time_col])
    df = df.set_index(time_col)
    df = df.sort_index()
    
    # Resample to hourly if needed
    ts = df[value_col].resample('H').mean().fillna(method='ffill')
    
    return ts


def find_optimal_parameters(ts: pd.Series, max_p: int = 3, max_d: int = 2, max_q: int = 3):
    """
    Find optimal SARIMAX parameters using AIC.
    
    Args:
        ts: Time series data
        max_p, max_d, max_q: Maximum values for p, d, q parameters
    
    Returns:
        Tuple of (p, d, q, P, D, Q, s) parameters
    """
    best_aic = np.inf
    best_params = None
    
    # Try different parameter combinations
    for p in range(max_p + 1):
        for d in range(max_d + 1):
            for q in range(max_q + 1):
                for P in range(2):
                    for D in range(2):
                        for Q in range(2):
                            try:
                                model = SARIMAX(
                                    ts,
                                    order=(p, d, q),
                                    seasonal_order=(P, D, Q, 24),  # 24-hour seasonality
                                    enforce_stationarity=False,
                                    enforce_invertibility=False
                                )
                                fitted_model = model.fit(disp=False, maxiter=50)
                                
                                if fitted_model.aic < best_aic:
                                    best_aic = fitted_model.aic
                                    best_params = (p, d, q, P, D, Q, 24)
                            except:
                                continue
    
    return best_params if best_params else (1, 1, 1, 0, 1, 1, 24)


def train_sarimax_model(
    data: pd.DataFrame,
    output_path: Optional[Path] = None
) -> SARIMAX:
    """
    Train SARIMAX model on time series data.
    
    Args:
        data: DataFrame with crime event data
        output_path: Path to save trained model
    
    Returns:
        Trained SARIMAX model
    """

    ts = prepare_timeseries_data(data)
    
    if len(ts) < 50:
        # Not enough data, use simple model
        order = (1, 1, 1)
        seasonal_order = (0, 1, 1, 24)
    else:
        # Find optimal parameters
        params = find_optimal_parameters(ts)
        order = params[:3]
        seasonal_order = params[3:]
    
    # Train model
    model = SARIMAX(
        ts,
        order=order,
        seasonal_order=seasonal_order,
        enforce_stationarity=False,
        enforce_invertibility=False
    )
    
    fitted_model = model.fit(disp=False, maxiter=100)
    
    # Save model
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            pickle.dump(fitted_model, f)
    
    return fitted_model


def load_sarimax_model(model_path: Path) -> SARIMAX:
    """Load trained SARIMAX model from file."""
    with open(model_path, 'rb') as f:
        return pickle.load(f)



