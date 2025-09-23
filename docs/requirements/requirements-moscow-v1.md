
# Sprint 1: Air Quality Website Development Proposal

### Requirement

Design a website for monitoring and analyzing air quality.

---

## 2.1. Project Overview

### Objective

Design and develop a website to monitor and analyze air quality with the ability to display real-time data and analyze trends.

### Scope

* Manage data from monitoring stations and open APIs
* Real-time dashboard
* Interactive map (select location coordinates to analyze)
* Basic analysis and charts
* User management
* Alert system
* Support report export

---

## 2.2. Air Quality Parameters to Monitor

### Core Pollutants (≥7 indicators)

* **PM2.5** – Fine particulate matter (≤2.5 micrometers)
* **PM10** – Coarse particulate matter (≤10 micrometers)
* **O3** – Ozone
* **NO2** – Nitrogen Dioxide
* **SO2** – Sulfur Dioxide
* **CO** – Carbon Monoxide
* **AQI** – Air Quality Index: calculated from the above pollutants and their potential health impacts.

Note: Although 7 pollutants are monitored, since **AQI** is aggregated from the other 6, the website only displays **AQI, PM2.5, and PM10**.

### Reference Standards

* **NAAQS (EPA)**: National Ambient Air Quality Standards, U.S. Environmental Protection Agency
* **WHO Air Quality Guidelines**: WHO-recommended levels based on scientific evidence
* **AQI Scale (0–500):**

  * 0–50: Good
  * 51–100: Moderate
  * 101–150: Unhealthy for sensitive groups
  * 151–200: Unhealthy
  * 201–300: Very Unhealthy
  * 301–500: Hazardous

### Data Sources

* **Primary**: Government monitoring stations
* **Secondary**: Open data API from [aqicn.org](https://aqicn.org)

---

## 2.3. Requirements Classified by MoSCoW

### MUST-HAVE

#### Functional Requirements

| Feature                 | Description                                                 | Acceptance Criteria                                                    |
| ----------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------- |
| Monitoring Station Mgmt | CRUD for stations with location info (city/zip/coordinates) | - Full CRUD API<br>- Input validation<br>- GPS coordinates supported   |
| Real-time Data Display  | Dashboard showing latest AQI, PM2.5, PM10                   | - Data updated ≤10 min<br>- Color coding by AQI<br>- Responsive design |
| Search by Location      | Search by city/zip/coordinates (e.g., zip 66000 – Lam Dong) | - Text search & geo-location<br>- Response ≤3s<br>- Autocomplete       |
| Basic Authentication    | Register/login with JWT and role-based access               | - JWT + refresh<br>- 3 roles: public, admin<br>- Password hashing      |
| Basic Analysis          | Data aggregation by day/month, average AQI                  | - MongoDB aggregation pipeline<br>- Trend charts<br>- Basic CSV export |

#### Non-Functional Requirements

| Type        | Requirement                           | Measurement                         |
| ----------- | ------------------------------------- | ----------------------------------- |
| Performance | Page load and API response            | ≤3s for common queries              |
| Security    | HTTPS, input validation, SQLi defense | 100% HTTPS, sanitized inputs        |
| Reliability | Uptime & data accuracy                | ≥99% uptime, data validation        |
| Usability   | Responsive, intuitive UI              | Mobile-friendly, WCAG AA compliance |

---

### SHOULD-HAVE

| Feature         | Description                                                           | Reason                        |
| --------------- | --------------------------------------------------------------------- | ----------------------------- |
| Alert System    | Email alerts when AQI exceeds thresholds                              | Health protection, engagement |
| Simple Forecast | 24h AQI forecast using Moving Average/Regression                      | Planning, competitive edge    |
| Interactive Map | Leaflet.js with color-coded AQI markers                               | Geographic visualization      |
| PDF Reports     | Export reports with charts and tables                                 | For authorities and research  |
| City Ranking    | City AQI ranking table                                                | Awareness and comparison      |
| Optimization    | Caching (Redis/Flask-Caching), DB indexing, materialized aggregations | Performance boost             |

---

### COULD-HAVE

* Advanced OpenAQ integration (real-time sync jobs)
* Advanced ML forecasting (XGBoost, LSTM)
* Mobile app (iOS/Android)
* Social features (comments, sharing)

---

### WON’T-HAVE

* Real-time streaming (SSE/WebSocket)
* Multi-tenant architecture
* Advanced visualizations (3D maps, AR)
* Blockchain integration
* AI chatbot
* Payment system
* Multilingual (other than Vietnamese)

---

## 2.4. Technical Architecture

* **Backend**: Flask (Python) + REST API
* **Database**: MongoDB (time-series, aggregation)
* **Frontend**: Flask Jinja2 + Bootstrap + Chart.js
* **Map**: Leaflet.js
* **Task Queue**: Celery (alerts & data sync)
* **Security**: JWT, HTTPS, input validation

---

## 2.5. Definition of Done (DoD)

* [ ] Feature works as per AC
* [ ] Unit test coverage ≥70%
* [ ] Integration tests pass
* [ ] Security scan has no critical issues
* [ ] Performance test passes (≤3s)
* [ ] Code review approved
* [ ] Documentation updated
* [ ] Cross-browser compatibility (Chrome, Firefox, Safari)
* [ ] Deployed to staging
* [ ] Database migration successful
* [ ] Monitoring & logging set up
* [ ] User acceptance testing completed

---

## 2.6. Risks & Mitigation

| Risk                       | Impact | Probability | Mitigation                               |
| -------------------------- | ------ | ----------- | ---------------------------------------- |
| OpenAQ API rate limits     | High   | Medium      | Caching, backup data                     |
| AQI calculation complexity | Medium | High        | Use official formulas, extensive testing |
| Data quality issues        | High   | Medium      | Validation, outlier detection            |
| Performance degradation    | Medium | Medium      | DB indexing, query optimization          |
| Security vulnerabilities   | High   | Low         | Security audits, input sanitization      |

---

## 2.7. Success Metrics

### Technical KPIs

* API response time ≤3s
* System uptime ≥99%
* Page load time ≤3s
* Zero critical vulnerabilities

### Business KPIs

* User registration rate
* Daily active users
* Alert subscription rate
* Data accuracy vs reference stations

---

