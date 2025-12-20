import { useEffect, useState, useCallback, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';
import { stationsApi, crimesApi, routingApi } from '../services/api';
import type { PoliceStation, CrimeEvent, RouteResponse } from '../types';
import RiskHeatmap from './RiskHeatmap';
import RouteDisplay from './RouteDisplay';

// Fix for default marker icons in React-Leaflet
const iconRetinaUrl = 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png';
const iconUrl = 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png';
const shadowUrl = 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png';

const DefaultIcon = L.icon({
  iconRetinaUrl,
  iconUrl,
  shadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  tooltipAnchor: [16, -28],
  shadowSize: [41, 41],
});

L.Marker.prototype.options.icon = DefaultIcon;

// Police station icon (blue)
const stationIcon = L.icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-blue.png',
  shadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
});

// Crime severity colors
const getCrimeColor = (severity: number): string => {
  if (severity >= 4) return 'red';
  if (severity >= 3) return 'orange';
  if (severity >= 2) return 'yellow';
  return 'green';
};

const createCrimeIcon = (severity: number) => {
  return L.icon({
    iconUrl: `https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-${getCrimeColor(severity)}.png`,
    shadowUrl,
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
  });
};

const MapContent = () => {
  const map = useMap();
  
  useEffect(() => {
    map.invalidateSize();
  }, [map]);

  return null;
};

// Crime Marker Cluster Component
const CrimeMarkerCluster = ({ crimes }: { crimes: CrimeEvent[] }) => {
  const map = useMap();
  const clusterRef = useRef<any>(null);

  useEffect(() => {
    if (!map || crimes.length === 0) {
      // Clean up if no crimes
      if (clusterRef.current) {
        map.removeLayer(clusterRef.current);
        clusterRef.current = null;
      }
      return;
    }

    // Load markercluster dynamically
    import('leaflet.markercluster').then((module) => {
      const MCG = (module as any).default?.MarkerClusterGroup || 
                  (module as any).MarkerClusterGroup ||
                  (L as any).markerClusterGroup;
      
      if (!MCG) {
        console.error('MarkerClusterGroup not available');
        return;
      }

      // Create marker cluster group
      const markerClusterGroup = new MCG({
        chunkedLoading: true,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        maxClusterRadius: 50,
        iconCreateFunction: (cluster: any) => {
          const count = cluster.getChildCount();
          return L.divIcon({
            html: `<div style="background-color: rgba(220, 38, 38, 0.8); color: white; border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 3px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">${count}</div>`,
            className: 'marker-cluster-custom',
            iconSize: L.point(40, 40),
          });
        },
      });

      // Add markers to cluster
      crimes
        .filter((crime) => crime.lat && crime.lng && crime.lat !== 0 && crime.lng !== 0)
        .forEach((crime) => {
          const circleMarker = L.circleMarker([crime.lat, crime.lng], {
            radius: 6,
            color: '#dc2626',
            fillColor: '#dc2626',
            fillOpacity: 0.8,
            weight: 2,
          });

          const popupContent = `
            <div>
              <strong>${crime.crime_type}</strong><br/>
              Şiddet: ${crime.severity}/5<br/>
              ${crime.street_name ? `Sokak: ${crime.street_name}<br/>` : ''}
              Tarih: ${new Date(crime.event_time).toLocaleString('tr-TR')}<br/>
              Güven: ${(crime.confidence_score * 100).toFixed(0)}%
            </div>
          `;
          circleMarker.bindPopup(popupContent);
          markerClusterGroup.addLayer(circleMarker);
        });

      map.addLayer(markerClusterGroup);
      clusterRef.current = markerClusterGroup;
    }).catch((err) => {
      console.error('Failed to load leaflet.markercluster:', err);
    });

    return () => {
      if (clusterRef.current) {
        map.removeLayer(clusterRef.current);
        clusterRef.current = null;
      }
    };
  }, [map, crimes]);

  return null;
};

const Map = () => {
  const [stations, setStations] = useState<PoliceStation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Risk map state
  const [showRiskMap, setShowRiskMap] = useState(false);
  const [riskStartTime, setRiskStartTime] = useState('');
  const [riskEndTime, setRiskEndTime] = useState('');
  const [riskThreshold, setRiskThreshold] = useState(0.3);
  
  // Crime events by date state
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [showCrimesByDate, setShowCrimesByDate] = useState(false);
  const [filteredCrimes, setFilteredCrimes] = useState<CrimeEvent[]>([]);
  const [loadingCrimes, setLoadingCrimes] = useState(false);
  
  // Route state
  const [route, setRoute] = useState<RouteResponse | null>(null);
  const [selectedStationId, setSelectedStationId] = useState<string>('');
  const [routeThreshold, setRouteThreshold] = useState(0.7);
  const [maxMinutes, setMaxMinutes] = useState(90);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const stationsRes = await stationsApi.list(true);
        setStations(stationsRes.data);
        if (stationsRes.data.length > 0) {
          setSelectedStationId(stationsRes.data[0].id);
        }
        setError(null);
      } catch (err) {
        setError('Veri yüklenirken hata oluştu');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  // Load crimes by selected date
  const loadCrimesByDate = useCallback(async (date: string) => {
    if (!date) {
      setFilteredCrimes([]);
      return;
    }

    try {
      setLoadingCrimes(true);
      // Seçilen tarihin başlangıç ve bitiş zamanları (UTC)
      // date format: "YYYY-MM-DD"
      const startDate = new Date(date + 'T00:00:00Z');
      const endDate = new Date(date + 'T23:59:59Z');

      const response = await crimesApi.list({
        start_time: startDate.toISOString(),
        end_time: endDate.toISOString(),
        limit: 1000,
      });
      
      setFilteredCrimes(response.data);
      setError(null);
    } catch (err) {
      setError('Olaylar yüklenirken hata oluştu');
      console.error(err);
      setFilteredCrimes([]);
    } finally {
      setLoadingCrimes(false);
    }
  }, []);

  // Tarih değiştiğinde veya göster butonu aktif olduğunda crime'ları yükle
  useEffect(() => {
    if (showCrimesByDate && selectedDate) {
      loadCrimesByDate(selectedDate);
    } else {
      setFilteredCrimes([]);
    }
  }, [selectedDate, showCrimesByDate, loadCrimesByDate]);

  const handleOptimizeRoute = async () => {
    if (!selectedStationId) {
      alert('Lütfen bir karakol seçin');
      return;
    }

    try {
      setLoading(true);
      const response = await routingApi.optimize({
        station_id: selectedStationId,
        risk_threshold: routeThreshold,
        max_minutes: maxMinutes,
      });
      setRoute(response.data);
      setError(null);
    } catch (err) {
      setError('Rota oluşturulurken hata oluştu');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Set default time range (next 24 hours)
  useEffect(() => {
    const now = new Date();
    const tomorrow = new Date(now);
    tomorrow.setHours(tomorrow.getHours() + 24);
    
    setRiskStartTime(now.toISOString().slice(0, 16));
    setRiskEndTime(tomorrow.toISOString().slice(0, 16));
  }, []);

  // Küçükçekmece center coordinates
  const center: [number, number] = [41.015, 28.75];

  return (
    <div style={{ width: '100%', height: '100vh', position: 'relative' }}>
      {/* Control Panel */}
      <div
        style={{
          position: 'absolute',
          top: '10px',
          right: '10px',
          zIndex: 1000,
          background: 'white',
          padding: '20px',
          borderRadius: '8px',
          boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
          maxWidth: '350px',
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
      >
        <h3 style={{ marginTop: 0, marginBottom: '15px' }}>Kontrol Paneli</h3>
        
        {/* Crime Events by Date Controls */}
        <div style={{ marginBottom: '20px', paddingBottom: '20px', borderBottom: '1px solid #eee' }}>
          <h4 style={{ marginTop: 0, marginBottom: '10px', fontSize: '14px' }}>Olayları Göster</h4>
          <div style={{ marginBottom: '10px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>
              Tarih Seç:
            </label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => {
                setSelectedDate(e.target.value);
              }}
              max={new Date().toISOString().split('T')[0]} // Bugünden önceki tarihler
              style={{ width: '100%', padding: '5px', fontSize: '12px', boxSizing: 'border-box' }}
            />
          </div>
          <button
            onClick={async () => {
              if (selectedDate) {
                const newShowState = !showCrimesByDate;
                setShowCrimesByDate(newShowState);
                if (newShowState) {
                  // Butona basıldığında crime'ları yükle
                  await loadCrimesByDate(selectedDate);
                }
              } else {
                alert('Lütfen bir tarih seçin');
              }
            }}
            disabled={!selectedDate || loadingCrimes}
            style={{
              width: '100%',
              padding: '8px',
              background: (!selectedDate || loadingCrimes) ? '#ccc' : (showCrimesByDate ? '#ff4444' : '#ff8800'),
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: (!selectedDate || loadingCrimes) ? 'not-allowed' : 'pointer',
              fontSize: '12px',
              fontWeight: '500',
            }}
          >
            {loadingCrimes ? 'Yükleniyor...' : (showCrimesByDate ? 'Olayları Gizle' : 'Olayları Göster')}
          </button>
          {showCrimesByDate && !loadingCrimes && filteredCrimes.length > 0 && (
            <div style={{ marginTop: '10px', fontSize: '11px', color: '#666', textAlign: 'center' }}>
              {filteredCrimes.length} olay bulundu
            </div>
          )}
          {showCrimesByDate && !loadingCrimes && filteredCrimes.length === 0 && selectedDate && (
            <div style={{ marginTop: '10px', fontSize: '11px', color: '#ff4444', textAlign: 'center' }}>
              Bu tarihte olay bulunamadı
            </div>
          )}
        </div>
        
        {/* Risk Map Controls */}
        <div style={{ marginBottom: '20px', paddingBottom: '20px', borderBottom: '1px solid #eee' }}>
          <h4 style={{ marginTop: 0, marginBottom: '10px', fontSize: '14px' }}>Risk Haritası</h4>
          <div style={{ marginBottom: '10px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>
              Başlangıç:
            </label>
            <input
              type="datetime-local"
              value={riskStartTime}
              onChange={(e) => setRiskStartTime(e.target.value)}
              style={{ width: '100%', padding: '5px', fontSize: '12px' }}
            />
          </div>
          <div style={{ marginBottom: '10px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>
              Bitiş:
            </label>
            <input
              type="datetime-local"
              value={riskEndTime}
              onChange={(e) => setRiskEndTime(e.target.value)}
              style={{ width: '100%', padding: '5px', fontSize: '12px' }}
            />
          </div>
          <div style={{ marginBottom: '10px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>
              Eşik: {(riskThreshold * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={riskThreshold}
              onChange={(e) => setRiskThreshold(parseFloat(e.target.value))}
              style={{ width: '100%' }}
            />
          </div>
          <button
            onClick={() => {
              if (riskStartTime && riskEndTime) {
                setShowRiskMap(!showRiskMap);
              } else {
                alert('Lütfen başlangıç ve bitiş tarihlerini seçin');
              }
            }}
            disabled={!riskStartTime || !riskEndTime}
            style={{
              width: '100%',
              padding: '8px',
              background: (!riskStartTime || !riskEndTime) ? '#ccc' : (showRiskMap ? '#ff4444' : '#0066ff'),
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: (!riskStartTime || !riskEndTime) ? 'not-allowed' : 'pointer',
              fontSize: '12px',
            }}
          >
            {showRiskMap ? 'Risk Haritasını Gizle' : 'Risk Haritasını Göster'}
            {riskStartTime && riskEndTime && new Date(riskStartTime) > new Date() && ' (Forecast)'}
          </button>
        </div>

        {/* Route Optimization Controls */}
        <div>
          <h4 style={{ marginTop: 0, marginBottom: '10px', fontSize: '14px' }}>Rota Optimizasyonu</h4>
          <div style={{ marginBottom: '10px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>
              Başlangıç Karakolu:
            </label>
            <select
              value={selectedStationId}
              onChange={(e) => setSelectedStationId(e.target.value)}
              style={{ width: '100%', padding: '5px', fontSize: '12px' }}
            >
              {stations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ marginBottom: '10px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>
              Risk Eşiği: {(routeThreshold * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={routeThreshold}
              onChange={(e) => setRouteThreshold(parseFloat(e.target.value))}
              style={{ width: '100%' }}
            />
          </div>
          <div style={{ marginBottom: '10px' }}>
            <label style={{ display: 'block', marginBottom: '5px', fontSize: '12px' }}>
              Maksimum Süre: {maxMinutes} dk
            </label>
            <input
              type="range"
              min="30"
              max="180"
              step="15"
              value={maxMinutes}
              onChange={(e) => setMaxMinutes(parseInt(e.target.value))}
              style={{ width: '100%' }}
            />
          </div>
          <button
            onClick={handleOptimizeRoute}
            disabled={loading || !selectedStationId}
            style={{
              width: '100%',
              padding: '8px',
              background: loading || !selectedStationId ? '#ccc' : '#00aa00',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: loading || !selectedStationId ? 'not-allowed' : 'pointer',
              fontSize: '12px',
            }}
          >
            {loading ? 'Yükleniyor...' : 'Rota Oluştur'}
          </button>
          {route && (
            <button
              onClick={() => setRoute(null)}
              style={{
                width: '100%',
                padding: '8px',
                marginTop: '10px',
                background: '#ff4444',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '12px',
              }}
            >
              Rotayı Temizle
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div
          style={{
            position: 'absolute',
            top: '10px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 1000,
            background: 'white',
            padding: '10px 20px',
            borderRadius: '5px',
            boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
          }}
        >
          Yükleniyor...
        </div>
      )}
      {error && (
        <div
          style={{
            position: 'absolute',
            top: '10px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 1000,
            background: '#ff4444',
            color: 'white',
            padding: '10px 20px',
            borderRadius: '5px',
            boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
          }}
        >
          {error}
        </div>
      )}
      <MapContainer
        center={center}
        zoom={13}
        minZoom={11}
        maxZoom={18}
        style={{ width: '100%', height: '100%' }}
        scrollWheelZoom={true}
        bounds={[[40.98, 28.70], [41.05, 28.80]]}
        maxBounds={[[40.95, 28.65], [41.08, 28.85]]}
      >
        <MapContent />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Risk Heatmap */}
        {showRiskMap && riskStartTime && riskEndTime && (
          <RiskHeatmap
            startTime={riskStartTime}
            endTime={riskEndTime}
            threshold={riskThreshold}
          />
        )}

        {/* Route Display */}
        {route && <RouteDisplay route={route} stationIcon={stationIcon} />}

        {/* Police Stations */}
        {stations.map((station) => (
          <Marker
            key={station.id}
            position={[station.lat, station.lng]}
            icon={stationIcon}
          >
            <Popup>
              <div>
                <strong>{station.name}</strong>
                <br />
                Kapasite: {station.capacity}
                <br />
                Durum: {station.active ? 'Aktif' : 'Pasif'}
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Crime Events - Show filtered crimes if date is selected, otherwise show none */}
        {showCrimesByDate && filteredCrimes.length > 0 && (
          <CrimeMarkerCluster crimes={filteredCrimes} />
        )}
      </MapContainer>
    </div>
  );
};

export default Map;

