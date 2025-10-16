# PlantUML Flow Diagrams - Air Quality Monitoring System

## Tổng quan

Thư mục này chứa các PlantUML diagrams mô tả các flows chính của hệ thống Air Quality Monitoring. Các diagrams được thiết kế **ngắn gọn, súc tích nhưng đầy đủ** các bước quan trọng.

## Danh sách Diagrams

### 0. System Overview (Recommended Start)
**File:** `flow_0_overview.puml`

**Mô tả:** Diagram tổng quan hiển thị tất cả 4 flows chính trong một view duy nhất.

**Nội dung:**
- Flow 1: Import Stations (one-time/periodic)
- Flow 2: Hourly Readings Ingestion (scheduled)
- Flow 3: Daily Forecasts Ingestion (scheduled)
- Flow 4: Backup & Restore (periodic/on-demand)

**Khuyến nghị:** Xem diagram này trước để hiểu tổng quan hệ thống.

---

### 1. Flow 1: Import Vietnam Stations
**File:** `flow_1_import_stations.puml`

**Mô tả:** Import/update thông tin trạm từ JSON → MongoDB `waqi_stations`.

**Key Points:**
- Validate & fix GeoJSON coordinates [lat,lon] → [lon,lat]
- Bulk upsert với compound key `_id`
- Idempotent operations

---

### 2. Flow 2: Station Readings Ingestion
**File:** `flow_2_station_readings.puml`

**Mô tả:** Thu thập real-time AQI data từ WAQI API (hourly schedule).

**Key Points:**
- Checkpoint mechanism (skip nếu đã xử lý trong giờ hiện tại)
- Rate limiting 1000 req/hour
- Compound key: `(station_idx, ts)`
- Update `latest_reading_at` field
- Time-series collection support

---

### 3. Flow 3: Forecast Data Ingestion
**File:** `flow_3_forecast_ingest.puml`

**Mô tả:** Thu thập dự báo 7 ngày cho tất cả trạm (daily schedule).

**Key Points:**
- Merge pollutant arrays (pm25, pm10, o3, uvi) by day
- Intelligent updates: skip nếu không có thay đổi
- Compound key: `(station_idx, day)`
- Track `last_forecast_run_at` timestamp

---

### 4. Flow 4a: Database Backup
**File:** `flow_4_backup.puml`

**Mô tả:** Sao lưu toàn bộ database → tar archive.

**Key Points:**
- Stream collections (batch 1000 docs)
- JSON Lines format (.jsonl)
- Preserve MongoDB types (ObjectId, ISODate)
- Save metadata (validators, timeseries config)
- Timestamped: `backup_YYYYMMDD_HHMMSS.tar`

---

### 5. Flow 4b: Database Restore
**File:** `flow_4_restore.puml`

**Mô tả:** Khôi phục database từ backup archive.

**Key Points:**
- Safety snapshot trước khi restore
- Confirmation prompt (type "YES")
- Time-series auto-detection
- Validator handling (disable/restore)
- Hash-based verification
- Dry-run mode available

---

## Cấu trúc Files

```
docs/plantuml/
├── README.md                      # Tài liệu này
├── flow_0_overview.puml          # ⭐ System Overview (xem đầu tiên)
├── flow_1_import_stations.puml   # Import stations
├── flow_2_station_readings.puml  # Hourly readings
├── flow_3_forecast_ingest.puml   # Daily forecasts
├── flow_4_backup.puml            # Database backup
└── flow_4_restore.puml           # Database restore
```

---

## Cách xem Diagrams

### Option 1: VS Code Extension (Recommended)

1. Install extension: **PlantUML** by jebbs
2. Install Java runtime (nếu chưa có)
3. Mở file `.puml` trong VS Code
4. Press `Alt+D` để preview diagram

### Option 2: Online Viewer

1. Copy nội dung file `.puml`
2. Paste vào: http://www.plantuml.com/plantuml/uml/
3. Xem diagram được render

### Option 3: PlantUML CLI

```bash
# Install PlantUML
# Download from https://plantuml.com/download

# Generate PNG
java -jar plantuml.jar flow_1_import_stations.puml

# Generate SVG
java -jar plantuml.jar -tsvg flow_1_import_stations.puml

# Generate all diagrams
java -jar plantuml.jar *.puml
```

### Option 4: Docker

```bash
# Run PlantUML server
docker run -d -p 8080:8080 plantuml/plantuml-server:jetty

# Truy cập http://localhost:8080 và paste diagram code
```

---

## Export Diagrams

### Export tất cả diagrams sang PNG:

```bash
# Từ thư mục docs/plantuml/
java -jar plantuml.jar -tpng *.puml
```

### Export sang SVG (scalable):

```bash
java -jar plantuml.jar -tsvg *.puml
```

### Export sang PDF:

```bash
java -jar plantuml.jar -tpdf *.puml
```

---

## Design Principles

Các diagrams được thiết kế theo nguyên tắc:

✅ **Ngắn gọn:** Tập trung vào main flow, bỏ qua chi tiết implementation  
✅ **Chính xác:** Mô tả đúng logic và data flow thực tế  
✅ **Đầy đủ:** Bao gồm tất cả bước quan trọng (không thiếu bước)  
✅ **Dễ hiểu:** Sử dụng notes để giải thích data structures  
✅ **Professional:** Theme plain, clean layout  

**Format:**
- **Participants:** User, Scripts, Services, Database
- **Notes:** Key data structures và compound keys
- **Alt/Loop:** Control flow khi cần thiết
- **Numbering:** Đánh số các bước chính (1, 2, 3...)

---

## Workflow đọc tài liệu

**Recommended Order:**

1. **`flow_0_overview.puml`** - Hiểu big picture của toàn bộ hệ thống
2. **`docs/data_flows.md`** - Đọc mô tả text chi tiết
3. **Individual flow diagrams** - Xem từng flow cụ thể khi cần
4. **`docs/db_schema.md`** - Hiểu cấu trúc collections

**Quick Reference:**
- Cần hiểu tổng quan → `flow_0_overview.puml`
- Cần chi tiết implementation → `docs/data_flows.md`
- Cần debug một flow → Individual flow diagram
- Cần biết schema → `docs/db_schema.md`

---

## Maintenance

Khi có thay đổi trong code:

1. Update diagram tương ứng trong `.puml` files
2. Đảm bảo sync với `docs/data_flows.md`
3. Re-generate images nếu cần
4. Commit cả `.puml` files và generated images

---

## Tips

### PlantUML Syntax Quick Reference

```plantuml
@startuml
' Comments start with '

' Define participants
participant "Name" as Alias

' Arrows
-> : synchronous call
->> : asynchronous call
--> : return message

' Activation
activate Participant
deactivate Participant

' Groups
alt condition
  ' true branch
else
  ' false branch
end

loop items
  ' loop body
end

' Notes
note left: text
note right: text
note over Participant: text

@enduml
```

### Color Themes

Current theme: `!theme plain` (black & white, professional)

Alternatives:
- `!theme cerulean` - Blue theme
- `!theme superhero` - Dark theme
- `!theme sketchy` - Hand-drawn style

---

## Troubleshooting

### "Syntax Error" khi preview

- Kiểm tra matching `@startuml` và `@enduml`
- Kiểm tra quotes đúng (`"`)
- Validate tại http://www.plantuml.com/plantuml/

### Diagram quá lớn

- Chia thành multiple diagrams nhỏ hơn
- Sử dụng `skinparam dpi 150` để tăng resolution
- Export sang SVG thay vì PNG

### Font issues

```plantuml
skinparam defaultFontName Arial
skinparam defaultFontSize 12
```

---

## Future Enhancements

Các diagrams có thể được mở rộng:

1. **Sequence Diagrams** cho API flows
2. **Component Diagrams** cho system architecture
3. **State Diagrams** cho data lifecycle
4. **Deployment Diagrams** cho production setup

---

## Contact

Nếu có câu hỏi về diagrams, liên hệ team hoặc tạo issue trong repo.
