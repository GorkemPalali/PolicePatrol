"""Overpass API client for fetching OSM data."""

import logging
import time
from typing import Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class OverpassClient:
    """Client for interacting with Overpass API."""

    def __init__(
        self,
        api_url: str = "https://overpass-api.de/api/interpreter",
        timeout: int = 300,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        """
        Initialize Overpass API client.

        Args:
            api_url: Overpass API endpoint URL
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.api_url = api_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Configure session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def build_bbox_query(
        self,
        bbox: Tuple[float, float, float, float],
        highway_tags: Optional[List[str]] = None,
    ) -> str:
        """
        Build Overpass QL query for bounding box.

        Args:
            bbox: Bounding box as (min_lat, min_lng, max_lat, max_lng)
            highway_tags: List of highway tag values to filter (e.g., ['motorway', 'trunk'])

        Returns:
            Overpass QL query string
        """
        min_lat, min_lng, max_lat, max_lng = bbox

        # Default highway tags if not specified
        if highway_tags is None:
            highway_tags = [
                "motorway",
                "trunk",
                "primary",
                "secondary",
                "tertiary",
                "residential",
                "service",
                "unclassified",
            ]

        # Build highway filter
        highway_filter = "|".join(highway_tags)
        highway_condition = f'["highway"~"^({highway_filter})$"]'

        # Overpass QL query
        query = f"""
[out:xml][timeout:300];
(
  way{highway_condition}({min_lat},{min_lng},{max_lat},{max_lng});
);
out geom;
"""

        return query

    def fetch_osm_data(
        self,
        bbox: Tuple[float, float, float, float],
        highway_tags: Optional[List[str]] = None,
    ) -> str:
        """
        Fetch OSM data from Overpass API.

        Args:
            bbox: Bounding box as (min_lat, min_lng, max_lat, max_lng)
            highway_tags: List of highway tag values to filter

        Returns:
            OSM XML data as string

        Raises:
            requests.RequestException: If request fails after retries
            ValueError: If bbox is invalid
        """
        if len(bbox) != 4:
            raise ValueError("Bbox must contain 4 values: (min_lat, min_lng, max_lat, max_lng)")

        min_lat, min_lng, max_lat, max_lng = bbox

        # Validate bbox
        if not (-90 <= min_lat <= 90) or not (-90 <= max_lat <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if not (-180 <= min_lng <= 180) or not (-180 <= max_lng <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        if min_lat >= max_lat or min_lng >= max_lng:
            raise ValueError("Invalid bbox: min values must be less than max values")

        # Build query
        query = self.build_bbox_query(bbox, highway_tags)
        logger.info(f"Fetching OSM data for bbox: {bbox}")

        # Make request
        try:
            response = self.session.post(
                self.api_url,
                data={"data": query},
                timeout=self.timeout,
                headers={"User-Agent": "PolicePatrol-OSM-Importer/1.0"},
            )
            response.raise_for_status()

            # Check for rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", self.retry_delay))
                logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                # Retry once more
                response = self.session.post(
                    self.api_url,
                    data={"data": query},
                    timeout=self.timeout,
                    headers={"User-Agent": "PolicePatrol-OSM-Importer/1.0"},
                )
                response.raise_for_status()

            logger.info(f"Successfully fetched OSM data ({len(response.text)} bytes)")
            return response.text

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout after {self.timeout} seconds")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch OSM data: {str(e)}")
            raise

    def check_api_status(self) -> Dict[str, any]:
        """
        Check Overpass API status.

        Returns:
            Dictionary with API status information
        """
        try:
            # Simple test query
            test_query = "[out:json][timeout:5];node(1);out;"
            response = self.session.post(
                self.api_url,
                data={"data": test_query},
                timeout=10,
                headers={"User-Agent": "PolicePatrol-OSM-Importer/1.0"},
            )
            response.raise_for_status()
            return {
                "status": "available",
                "url": self.api_url,
                "response_time_ms": response.elapsed.total_seconds() * 1000,
            }
        except Exception as e:
            return {
                "status": "unavailable",
                "url": self.api_url,
                "error": str(e),
            }

