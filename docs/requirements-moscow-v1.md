<<<<<<< HEAD

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
=======
**# Air Quality Website Development Proposal**



**\*\*Request:\*\* Design a website for monitoring and analyzing air quality.**



**## 1. Project Overview**



**### Objectives**



**Design and develop a website for monitoring and analyzing air quality with the ability to display real-time data, trend analysis**



**### Scope**



**· Manage data from monitoring stations and open APIs**  

**· Real-time dashboard**  

**· Map (select coordinates of locations to analyze)**  

**· Basic analysis and charts**  

**· User management**  

**· Alert system**  

**· Support for exporting reports**  



**## 2. Air quality parameters to monitor**



**Core pollutants (≥7 indicators)**  

**1. PM2.5 - Fine dust particles (≤2.5 micrometers)**  

**2. PM10 - Coarse dust particles (≤10 micrometers)**  

**3. O3 - Ozone**  

**4. NO2 - Nitrogen Dioxide**  

**5. SO2 - Sulfur Dioxide**  

**6. CO - Carbon Monoxide**  

**7. AQI - Air Quality Index (Air quality index): built based on the relationship between the concentrations of pollutants and potential impacts on health.**  



**\*\*Note:\*\* There are up to 7 air quality parameters to monitor, but since AQI is aggregated from the remaining 6 parameters, the website only displays AQI, PM 2.5 and PM 10.**



**### Reference standards**



**· NAAQS (National Ambient Air Quality Standards) from EPA: air quality standards established by the United States Environmental Protection Agency (EPA). Its role is a legal tool to manage and control air pollution in the US.**  

**· WHO Air Quality Guidelines: Air quality standards of the World Health Organization (WHO) are a set of recommendations based on scientific evidence on safe levels of air pollution for human health.**  

**· AQI Scale: 0-500 (0-50: Good, 51-100: Moderate, 101-150: Unhealthy for sensitive groups, 151-200: Unhealthy, 201-300: Very unhealthy, 301-500: Hazardous)**  



**### Data sources**



**· Primary: Government monitoring stations**  

**· Secondary: API (open data) from aqicn.org**  



**## 3. Requirement classification according to MoSCoW**



**### MUST-HAVE** 



**#### Functional requirements**



**| Feature                  | Detailed description                                                                 | Acceptance Criteria                                                                 |**

**|--------------------------|--------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|**

**| Manage monitoring stations | CRUD monitoring stations with location information (city/zip/coordinates)            | - Full CRUD API endpoints<br>- Input data validation<br>- Support GPS coordinates  |**

**| Display real-time data   | Dashboard displaying the latest AQI and 2 pollution indicators (PM 2.5, PM 10)       | - Data update ≤10 minutes<br>- Color coding according to AQI thresholds<br>- Responsive design |**

**| Search by location       | Search by city/zip code/coordinates (e.g.: zip 66000 for Lâm Đồng)                   | - Support text search and geo-location<br>- Results returned ≤3 seconds<br>- Autocomplete suggestions |**

**| Basic authentication     | Registration/login with JWT and role-based access                                    | - JWT token with refresh<br>- 3 roles: public, admin <br>- Password hashing        |**

**| Basic analysis           | Data aggregation by day/month, average AQI                                           | - MongoDB aggregation pipeline<br>- Charts displaying trends<br>- Basic CSV export |**



**#### Non-functional requirements**



**| Type       | Requirement                                 | Measurement indicator                       |**

**|------------|---------------------------------------------|---------------------------------------------|**

**| Performance| Page load and API response                  | ≤3 seconds for common queries               |**

**| Security   | HTTPS, input validation, SQL injection prevention | 100% HTTPS, sanitized inputs                |**

**| Reliability| Uptime and data accuracy                    | ≥99% uptime, data validation                |**

**| Usability  | Responsive design, intuitive UI             | Mobile-friendly, WCAG AA compliance         |**



**### SHOULD-HAVE**



**#### Advanced features**



**| Feature          | Description                                                             | Priority reason                     |**

**|------------------|-------------------------------------------------------------------------|-------------------------------------|**

**| Alert system     | Email alerts when AQI exceeds custom thresholds                         | Protect public health, increase engagement |**

**| Simple forecasting | Forecast AQI 24h using Moving Average/Linear Regression                 | Support planning, competitive advantage |**

**| Interactive map  | Leaflet.js with markers displaying AQI by color                         | Visualize geographic data           |**

**| PDF reports      | Export reports with charts and tables                                   | Serve management agencies and research |**

**| City ranking     | Ranking table of cities by AQI                                          | Create awareness and comparison     |**



**#### Optimization**



**· Caching for common queries (Redis/Flask-Caching)**  

**· Database indexing for performance**  

**· Materialized aggregations for quick reports**  



**### COULD-HAVE (Possible - Post-MVP)**



**| Feature                  | Description                                           | Condition                          |**

**|--------------------------|-------------------------------------------------------|------------------------------------|**

**| Advanced OpenAQ integration | Real-time sync with scheduled jobs                    | If there is time and resources     |**

**| Advanced ML forecasting  | XGBoost, LSTM for accurate forecasting                | If there is data scientist         |**

**| Mobile app               | Native iOS/Android app                                | If there is budget for mobile development |**

**| Social features          | Comments, sharing, community features                 | If need to increase user engagement |**



**### WON'T-HAVE** 



**· Real-time streaming (SSE/WebSocket) - high complexity**  

**· Multi-tenant architecture - not necessary for MVP**  

**· Advanced data visualization (3D maps, AR) - overkill**  

**· Blockchain integration - not suitable for use case**  

**· AI chatbot - not priority**  

**· Payment system - business model not clear**  

**· Multi-language besides Vietnamese**  



**## 4. Technical architecture**



**### Tech Stack**



**· Backend: Flask (Python) + REST API**  

**· Database: MongoDB (time-series data, aggregation)**  

**· Frontend: Flask Jinja2 + Bootstrap + Chart.js**  

**· Map: Leaflet.js**  

**· Task Queue: Celery (for alerts \& data sync)**  

**· Security: JWT, HTTPS, input validation**  



**## 5. Definition of Done (DoD)**



**### Function**



**· Feature operates according to defined AC: ensure the feature operates according to the specified AC requirements.**  

**· Unit tests coverage ≥70%: require unit tests to cover at least 70% of the source code.**  

**· Integration tests pass: Ensure integration tests run successfully to check interactions between modules or different systems (e.g.: frontend and backend, application with database).**  

**· Security scan has no critical issues.**  

**· Performance test meets requirements (≤3s): Ensure the feature meets performance requirements, for example, page load time not exceeding 3 seconds.**  



**### Quality**



**· Code review approved: require code to be reviewed and approved by other team members, helping improve quality, discussion, knowledge sharing, and early error detection.**  

**· Documentation updated: ensure all documents such as API, configuration guides, business research documents, … are compiled and updated.**  

**· Browser compatibility (Chrome, Firefox, Safari): Ensure the feature operates stably and consistently on the most popular web browsers.**  



**### Deployment**



**· Deployed to staging environment: The feature has been successfully deployed to the staging environment**  

**· Database migration successful: Ensure that all changes to the database structure have been applied successfully without errors.**  

**· Monitoring \& logging configured: Set up monitoring and logging system to track feature performance and detect issues in the real environment.**  

**· User acceptance testing completed: Ensure the feature has been tested and accepted by end users or third parties. This is the final step to confirm that the feature meets user needs.**  



**## 6. Risks \& Mitigation**



**| Risk                       | Impact | Probability | Mitigation                              |**

**|----------------------------|--------|-------------|-----------------------------------------|**

**| OpenAQ API rate limits     | High   | Medium      | Implement caching, backup data sources  |**

**| AQI calculation complexity | Medium | High        | Use established formulas, extensive testing |**

**| Data quality issues        | High   | Medium      | Implement data validation, outlier detection |**

**| Performance degradation    | Medium | Medium      | Database indexing, query optimization   |**

**| Security vulnerabilities   | High   | Low         | Regular security audits, input sanitization |**



**## 7. Success Metrics**



**### Technical KPIs**



**· API response time ≤3 seconds**  

**· System uptime ≥99%**  

**· Page load time ≤3 seconds**  

**· Zero critical security vulnerabilities**  



**### Business KPIs**



**· User registration rate**  

**· Daily active users**  

**· Alert subscription rate**  

**· Data accuracy vs reference stations**
>>>>>>> 3dc63b0 (Add Moscow requirements draft)

