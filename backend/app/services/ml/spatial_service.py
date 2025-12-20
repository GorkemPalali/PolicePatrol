from typing import Optional
from pathlib import Path
import numpy as np

try:
    from sklearn.linear_model import LinearRegression
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


def forecast_spatial_temporal(
    spatial_features: np.ndarray,
    temporal_features: np.ndarray,
    model_path: Optional[Path] = None
) -> np.ndarray:
    """
    Forecast risk using spatial-temporal model.
    
    Args:
        spatial_features: Spatial feature matrix
        temporal_features: Temporal feature matrix
        model_path: Path to pre-trained model (optional)
    
    Returns:
        Forecasted risk scores
    """
    if spatial_features.size == 0:
        return np.array([0.0])
    
    # If no model available, use simple spatial average
    if not SKLEARN_AVAILABLE or not model_path or not model_path.exists():
        # Simple spatial average with temporal weighting
        if len(spatial_features.shape) > 1:
            spatial_avg = np.mean(spatial_features, axis=0)
        else:
            spatial_avg = np.array([np.mean(spatial_features)])
        
        # Apply temporal weighting if available
        if temporal_features.size > 0:
            # Use hour of day as weight (higher risk at night)
            if len(temporal_features.shape) > 1:
                hour_sin = temporal_features[:, 0] if temporal_features.shape[1] > 0 else np.array([0.5])
                # Convert sin back to approximate hour (0-23)
                hour_approx = np.arcsin(np.clip(hour_sin, -1, 1)) * 24 / (2 * np.pi)
                # Night hours (22-6) get higher weight
                night_weight = np.where((hour_approx >= 22) | (hour_approx <= 6), 1.2, 1.0)
                return spatial_avg * np.mean(night_weight)
        
        return spatial_avg
    
    # Use trained model
    try:
        import pickle
        with open(model_path, 'rb') as f:
            model_dict = pickle.load(f)
        
        # Combine features
        if len(spatial_features.shape) == 1:
            spatial_features = spatial_features.reshape(1, -1)
        if len(temporal_features.shape) == 1:
            temporal_features = temporal_features.reshape(1, -1)
        
        combined = np.hstack([
            spatial_features[:, :model_dict['spatial_dim']],
            temporal_features[:, :model_dict['temporal_dim']]
        ])
        
        # Predict
        predictions = np.dot(combined, model_dict['weights']) + model_dict['intercept']
        return np.clip(predictions, 0.0, 1.0)
    
    except Exception:
        # Fallback on error
        if len(spatial_features.shape) > 1:
            return np.mean(spatial_features, axis=0)
        return np.array([np.mean(spatial_features)])
