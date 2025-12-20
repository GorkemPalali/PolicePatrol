# Predictive Patrol Routing System (PPRS)

Suç risk tahmini ve devriye rotası optimizasyonu sistemi.

## Özellikler

- **Risk Forecasting**: Geçmiş suç verilerine dayalı mekansal-zamansal risk haritaları
- **Adaptive KDE**: Yerel olay yoğunluğuna göre ayarlanan kernel density estimation
- **Grid-based Risk Cells**: Hex veya square grid tabanlı risk hücreleri
- **Route Optimization**: Risk-aware devriye rotası optimizasyonu
- **Interactive Map**: Leaflet tabanlı interaktif harita arayüzü
- **Küçükçekmece Sınırları**: Sistem Küçükçekmece ilçesi sınırları içinde çalışır

## Teknoloji Stack

### Backend
- Python 3.11
- FastAPI
- PostgreSQL 15+ with PostGIS 3.x
- Redis
- SQLAlchemy
- scikit-learn, statsmodels

### Frontend
- React 18
- TypeScript
- Leaflet / react-leaflet
- Vite

### Database
- PostgreSQL 15+
- PostGIS 3.x
- pgRouting

## Coğrafi Sınırlar

Sistem **Küçükçekmece, İstanbul** ilçesi sınırları içinde çalışacak şekilde yapılandırılmıştır:

- **Polygon Boundary**: Küçükçekmece ilçe sınırları OSM'den çekilip polygon olarak veritabanında saklanır
- **Fallback Bounding Box** (polygon yoksa): 
  - Min Lat: 40.98
  - Min Lng: 28.70
  - Max Lat: 41.05
  - Max Lng: 28.80

Risk haritaları ve rota optimizasyonu polygon sınırları içinde gerçekleştirilir. İlk kurulumda boundary otomatik olarak import edilir.

### Otomatik Sınır Validasyonu

Sistem, Küçükçekmece sınırları dışındaki verilerin eklenmesini/güncellenmesini **otomatik olarak engeller**:

- **API Seviyesi**: CREATE ve UPDATE endpoint'lerinde koordinatlar kontrol edilir
  - Sınır dışı veri eklenmeye çalışılırsa **HTTP 400 Bad Request** hatası döner
  - Hata mesajı: "Koordinatlar Küçükçekmece sınırları dışında"
- **Database Seviyesi**: BEFORE INSERT/UPDATE trigger'ları ile ek güvenlik katmanı
  - API bypass edilse bile veritabanı seviyesinde koruma sağlar
  - Sınır dışı veri eklenmeye çalışılırsa PostgreSQL exception fırlatılır

**Etkilenen Tablolar:**
- `crime_event`: Suç olayları koordinatları
- `police_station`: Polis karakolu koordinatları
- `risk_cell`: Risk hücresi geometrileri (opsiyonel)

**Validation'ı Devre Dışı Bırakma:**
Development ortamında validation'ı kapatmak için `.env` dosyasına ekleyin:
```env
STRICT_BOUNDARY_VALIDATION=false
```

**Mevcut Sınır Dışı Verileri Temizleme:**
Mevcut veritabanındaki sınır dışı verileri temizlemek için:
```bash
# Önce rapor al (dry-run)
python3 scripts/cleanup_out_of_boundary_data.py --dry-run

# Gerçekten temizle
python3 scripts/cleanup_out_of_boundary_data.py --force
```

## Kurulum

### Gereksinimler

- Docker & Docker Compose
- Node.js 20+ (local development için)
- Python 3.11+ (local development için)

### İlk Kurulum

1. **Repository'yi clone edin:**
```bash
git clone https://github.com/GorkemPalali/PolicePatrol.git
cd PolicePatrol
```

2. **Environment dosyasını oluşturun:**
```bash
cp env.example .env
```

3. **`.env` dosyasını düzenleyin ve güvenli şifreler belirleyin:**
   ```bash
   # ÖNEMLİ: Production ortamında mutlaka güçlü şifreler kullanın!
   # .env dosyasını düzenleyin ve aşağıdaki değerleri değiştirin:
   
   POSTGRES_PASSWORD=<güvenli_şifre_buraya>
   DATABASE_URL=postgresql+psycopg2://police:<güvenli_şifre_buraya>@db:5432/policepatrol
   ```
   
   **Güvenlik Notları:**
   - `POSTGRES_PASSWORD`: En az 16 karakter, büyük/küçük harf, rakam ve özel karakter içeren güçlü bir şifre kullanın
   - `DATABASE_URL`: `POSTGRES_PASSWORD` ile aynı şifreyi kullanın
   - `.env` dosyası `.gitignore`'da olduğu için Git'e commit edilmeyecektir
   - Production ortamında şifreleri environment variable olarak veya secret management sistemi ile yönetin

4. **Docker ile çalıştırın:**
```bash
docker compose up -d
```

5. **Logları kontrol edin:**
```bash
docker compose logs -f
```

6. **Servislerin çalıştığını doğrulayın:**
```bash
# Backend health check
curl http://localhost:8000/api/v1/health

# Frontend (tarayıcıda açın)
# http://localhost:5173
```

## Güvenlik

### Environment Variables ve Şifre Yönetimi

**ÖNEMLİ:** Bu proje production ortamında kullanılmadan önce aşağıdaki güvenlik önlemlerini alın:

1. **`.env` Dosyası:**
   - `.env` dosyası Git'e commit edilmez (`.gitignore`'da)
   - Her ortam için farklı `.env` dosyası kullanın
   - Production ortamında şifreleri environment variable olarak veya secret management sistemi (AWS Secrets Manager, HashiCorp Vault, vb.) ile yönetin

2. **Şifre Güvenliği:**
   - `POSTGRES_PASSWORD`: En az 16 karakter, karmaşık şifre kullanın
   - Production'da düzenli olarak şifreleri değiştirin
   - Şifreleri kod içinde veya version control'de saklamayın
   - `docker-compose.yml` dosyasında hardcoded şifre yoktur (güvenlik önlemi)

3. **Database Güvenliği:**
   - Production'da PostgreSQL portunu (5432) dışarıya açmayın
   - Sadece gerekli servislerin database'e erişmesine izin verin
   - SSL/TLS bağlantıları kullanın

4. **Network Güvenliği:**
   - Docker network'lerini doğru yapılandırın
   - Gereksiz port açıklıklarını kapatın
   - Firewall kurallarını uygulayın

### Docker ile Çalıştırma

```bash
# Servisleri başlat
docker compose up -d

# Logları izle
docker compose logs -f

# Servisleri durdur
docker compose stop

# Servisleri kaldır (veriler korunur)
docker compose down

# Servisleri kaldır ve volume'ları sil
docker compose down -v
```

**Servisler:**
- Backend API: http://localhost:8000
- Frontend: http://localhost:5173
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### Local Development

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Root dizindeki .env dosyasını kullanın veya backend/.env oluşturun
# DATABASE_URL ve REDIS_URL .env dosyasından okunacak

# Uygulamayı çalıştır
uvicorn app.main:app --reload
```

**Not:** Backend, root dizindeki `.env` dosyasını otomatik olarak okur. Eğer farklı bir konum kullanmak isterseniz, `backend/app/core/config.py` dosyasını düzenleyin.

#### Frontend

```bash
cd frontend
npm install

# Root dizindeki .env dosyasındaki VITE_API_BASE_URL kullanılır
# Veya frontend/.env.local oluşturabilirsiniz

# Development server
npm run dev
```

**Not:** Frontend için environment değişkenleri `VITE_` prefix'i ile başlamalıdır.

## Veri Import

JSONL formatındaki suç verilerini import etmek için:

```bash
# Docker container içinde
docker compose cp /path/to/crime.jsonl backend:/tmp/crime.jsonl
docker compose cp scripts/import_crimes_jsonl.py backend:/app/import_crimes_jsonl.py
docker compose exec backend python /app/import_crimes_jsonl.py /tmp/crime.jsonl

# Veya local'de (venv aktifken)
cd backend
python ../scripts/import_crimes_jsonl.py /path/to/crime.jsonl
```

## API Endpoints

### Health Check
- `GET /api/v1/health` - Sistem durumu

### Police Stations
- `GET /api/v1/stations` - Karakol listesi
- `GET /api/v1/stations/{id}` - Karakol detayı
- `POST /api/v1/stations` - Yeni karakol ekle
  - **Validation**: Koordinatlar Küçükçekmece sınırları içinde olmalı (HTTP 400 if outside)
- `PATCH /api/v1/stations/{id}` - Karakol güncelle
  - **Validation**: Yeni koordinatlar Küçükçekmece sınırları içinde olmalı (HTTP 400 if outside)
- `DELETE /api/v1/stations/{id}` - Karakol sil (soft delete)

### Crime Events
- `GET /api/v1/crimes` - Suç olayları listesi (filtreleme ile)
- `GET /api/v1/crimes/{id}` - Suç olayı detayı
- `POST /api/v1/crimes` - Yeni suç olayı ekle
  - **Validation**: Koordinatlar Küçükçekmece sınırları içinde olmalı (HTTP 400 if outside)
- `PATCH /api/v1/crimes/{id}` - Suç olayı güncelle
  - **Validation**: Yeni koordinatlar Küçükçekmece sınırları içinde olmalı (HTTP 400 if outside)
- `DELETE /api/v1/crimes/{id}` - Suç olayı sil

### Risk Forecast
- `GET /api/v1/forecast/risk-map` - Risk haritası oluştur
  - Query params: `start_time`, `end_time`, `threshold`, `grid_size_m`, `use_hex`
  - **Sınır**: Küçükçekmece bounding box içinde
- `WS /api/v1/realtime/risk-updates` - Real-time risk güncellemeleri (WebSocket)
  - Query params: `start_time`, `end_time`, `bbox` (opsiyonel)
  - Yeni crime event eklendiğinde otomatik risk güncellemesi gönderir
  - Heartbeat mesajları ile bağlantı durumu kontrol edilir

### Route Optimization
- `POST /api/v1/routing/optimize` - Devriye rotası oluştur (tek merkez)
  - Body: `station_id`, `risk_threshold`, `max_minutes`, `end_station_id` (opsiyonel)
  - **Sınır**: Küçükçekmece sınırları içindeki risk hücreleri kullanılır
- `POST /api/v1/routing/optimize-multi` - Koordineli devriye rotaları oluştur (çoklu merkez)
  - Body: `station_ids` (opsiyonel, None = tüm aktif merkezler), `risk_threshold`, `max_minutes_per_station`, `minimize_overlap`, `distribute_by_capacity`
  - **Özellikler**: Risk hücrelerini merkezler arasında dağıtır, overlap'i minimize eder
  - **Response**: Her merkez için rota, toplam risk kapsamı, overlap yüzdesi, koordinasyon skoru

### ML Forecast
- `GET /api/v1/ml-forecast/timeseries` - Time-series forecast
- `GET /api/v1/ml-forecast/spatial-temporal` - Spatial-temporal forecast
- `GET /api/v1/ml-forecast/ensemble` - Ensemble forecast

### OSM Import
- `GET /api/v1/osm/status` - OSM import ve topology durumu
- `POST /api/v1/osm/import` - OSM verilerini import et
- `POST /api/v1/osm/refresh-topology` - Topology'yi yeniden oluştur
- `GET /api/v1/osm/topology-status` - Topology durumu
- `POST /api/v1/osm/import-boundary` - Küçükçekmece boundary'sini import et
- `GET /api/v1/osm/boundary-status` - Boundary durumu

## Database Schema

### Tablolar

- `crime_event`: Suç olayları
- `police_station`: Polis karakolları
- `road_segment`: Yol segmentleri (OSM'den, routing için)
- `risk_cell`: Grid-based risk hücreleri
- `administrative_boundary`: İdari sınırlar (polygon olarak, Küçükçekmece için)

### Indexler

- GiST indexler: Tüm geometry kolonları
- B-tree indexler: Temporal ve categorical kolonlar
- Composite indexler: Spatio-temporal queries için

## OSM Verileri ve Boundary

### Küçükçekmece Boundary (Polygon)

Küçükçekmece ilçe sınırları OSM'den çekilip **polygon** olarak `administrative_boundary` tablosunda saklanır. Docker container başlatıldığında otomatik olarak import edilir.

**Manuel Import:**
```bash
# API endpoint ile
curl -X POST http://localhost:8000/api/v1/osm/import-boundary

# Script ile
python3 scripts/import_kucukcekmece_boundary.py
```

### OSM Road Data

OSM (OpenStreetMap) verileri `road_segment` tablosuna **otomatik olarak** import edilir. Küçükçekmece polygon sınırları içindeki yol ağı verileri kullanılır.

### Otomatik Import

Docker container başlatıldığında, sistem otomatik olarak:
1. Küçükçekmece boundary'sini OSM'den çekip polygon olarak saklar
2. Overpass API'den Küçükçekmece polygon bölgesi için OSM yol verilerini çeker
3. Verileri parse edip `road_segment` tablosuna import eder (polygon içinde filtreleme yapılır)
4. pgRouting topology'sini otomatik olarak oluşturur

**Not:** Eğer veriler zaten mevcutsa, import atlanır (idempotent).

### Manuel Import

OSM verilerini manuel olarak import etmek için API endpoint'lerini kullanabilirsiniz:

```bash
# Import durumunu kontrol et
curl http://localhost:8000/api/v1/osm/status

# OSM verilerini import et
curl -X POST http://localhost:8000/api/v1/osm/import \
  -H "Content-Type: application/json" \
  -d '{
    "clear_existing": false,
    "create_topology": true
  }'

# Topology'yi yeniden oluştur
curl -X POST http://localhost:8000/api/v1/osm/refresh-topology?force=true
```

### API Endpoints

- `GET /api/v1/osm/status` - OSM import ve topology durumu
- `POST /api/v1/osm/import` - OSM verilerini import et
  - Body: `{"clear_existing": false, "create_topology": true, "bbox": [40.98, 28.70, 41.05, 28.80]}`
- `POST /api/v1/osm/refresh-topology?force=true` - Topology'yi yeniden oluştur
- `GET /api/v1/osm/topology-status` - Topology durumu

### Yapılandırma

OSM import ayarları `.env` dosyasında veya `backend/app/core/config.py` içinde yapılandırılabilir:

```env
# Overpass API endpoint
OVERPASS_API_URL=https://overpass-api.de/api/interpreter

# Docker başlangıcında otomatik import
OSM_IMPORT_ON_STARTUP=true

# Import edilecek highway tag'leri (virgülle ayrılmış)
OSM_HIGHWAY_TAGS=motorway,trunk,primary,secondary,tertiary,residential,service,unclassified

# pgRouting topology tolerance (derece cinsinden, varsayılan: 0.0001 ~ 11 metre)
OSM_TOPOLOGY_TOLERANCE=0.0001
```

### Eski Yöntem (Manuel)

Eğer otomatik import çalışmazsa, manuel olarak:

1. Overpass API veya Planetiler kullanarak Küçükçekmece bölgesi için veri çekin
2. `road_segment` tablosuna import edin
3. `database/routing_setup.sql` script'ini çalıştırarak pgRouting topology oluşturun

## Geliştirme Notları

### Risk Forecasting

Risk hücreleri oluşturulurken:
1. Temporal features (hour, day, weekend) çıkarılır
2. Adaptive KDE ile mekansal yoğunluk hesaplanır
3. Grid-based hücreler oluşturulur (hex veya square)
4. Her hücre için risk skoru ve confidence hesaplanır
5. **Sadece Küçükçekmece sınırları içindeki hücreler oluşturulur**

### Route Optimization

Rota optimizasyonu:
1. Yüksek riskli hücreler belirlenir (Küçükçekmece sınırları içinde)
2. Hücreler cluster'lara ayrılır
3. pgRouting ile en kısa yol hesaplanır
4. Risk-aware cost function uygulanır

## Real-time Risk Updates

Sistem, WebSocket tabanlı real-time risk güncellemeleri destekler:

### Özellikler

- **Otomatik Güncelleme**: Yeni crime event eklendiğinde risk haritası otomatik olarak hesaplanır ve tüm bağlı client'lara broadcast edilir
- **Redis Cache**: Risk hesaplamaları Redis'te cache'lenir (TTL: 1 saat)
- **WebSocket Bağlantısı**: Frontend WebSocket ile bağlanır ve real-time güncellemeleri alır
- **Heartbeat**: Bağlantı durumu heartbeat mesajları ile kontrol edilir
- **Auto-reconnection**: Bağlantı koptuğunda otomatik yeniden bağlanma

### Kullanım

**Backend:**
- WebSocket endpoint: `WS /api/v1/realtime/risk-updates`
- Yeni crime event eklendiğinde otomatik olarak risk güncellemesi tetiklenir

**Frontend:**
- `RiskHeatmap` component'i `enableRealtime` prop'u ile real-time güncellemeleri aktif edebilir
- WebSocket client otomatik olarak bağlanır ve güncellemeleri dinler

### Yapılandırma

`.env` dosyasında:
```env
# Real-time updates
REALTIME_ENABLED=true
RISK_CACHE_TTL_SECONDS=3600
WEBSOCKET_HEARTBEAT_INTERVAL=30
RISK_UPDATE_BROADCAST_ENABLED=true
```

## Multi-Station Route Coordination

Sistem, birden fazla polis merkezi için koordineli devriye rotaları oluşturma özelliğine sahiptir:

### Özellikler

- **Risk Hücresi Dağılımı**: Risk hücrelerini merkezler arasında optimal şekilde dağıtır
  - Coğrafi yakınlık (distance-based)
  - Merkez kapasitesi (capacity-based)
  - Risk skoru (risk-based)
- **Overlap Minimizasyonu**: Rotalar arasındaki çakışmaları minimize eder
- **Koordinasyon Skoru**: Rotaların ne kadar iyi koordine edildiğini gösterir (0.0-1.0)

### Kullanım

**API Endpoint:**
```bash
POST /api/v1/routing/optimize-multi
{
  "station_ids": null,  # null = tüm aktif merkezler
  "risk_threshold": 0.7,
  "max_minutes_per_station": 90,
  "minimize_overlap": true,
  "distribute_by_capacity": true
}
```

**Yapılandırma:**
```env
MULTI_STATION_COORDINATION_ENABLED=true
DEFAULT_OVERLAP_THRESHOLD=0.2
CAPACITY_WEIGHT=0.3
DISTANCE_WEIGHT=0.4
RISK_WEIGHT=0.3
```

### Frontend

`MultiRouteDisplay` component'i birden fazla rotayı aynı anda görüntüler:
- Her merkez için farklı renk
- Overlap bilgisi gösterimi
- Koordinasyon skoru gösterimi

## Gelecek Geliştirmeler

- [x] OSM verilerinin otomatik import'u
- [x] Küçükçekmece sınırlarının polygon olarak saklanması
- [x] Sınır dışı verilerin otomatik filtrelenmesi
- [x] Real-time risk updates
- [x] Multi-station route coordination

## Lisans

Bu proje UNDP & SAMSUNG INNOVATION AI CAMPUS kapsamında bitirme projesi olarak geliştirilmiştir.