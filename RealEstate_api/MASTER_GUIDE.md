# Real Estate & Property API: Technical Master Guide

## 📌 Project Overview
The **Real Estate API** is a specialized FastAPI service designed to bridge modern property management workflows with the **Odoo 18.0** enterprise engine. It enables property dealers to list assets, track agents, and manage customer leads seamlessly.

## 🏗 Architectural Blueprint

### 1. Data Mapping (Odoo ↔ API)
To ensure production reliability, we mapped real estate entities to proven Odoo core models:
- **Properties**: Managed as `product.template` records with a "Real Estate" category.
- **Inquiries**: Directly integrated with the `crm.lead` model (CRM App).
- **Agents**: Stored as `res.partner` records with a custom "Agent" tag.

### 2. Security Architecture
The system uses a **Dual-Token JWT** implementation:
- **Access Tokens**: Short-lived (60m) for high security.
- **Refresh Tokens**: Long-lived (7d) for seamless user experience.
- **Role Enforcement**: API endpoints are guarded by `Depends(get_current_user)` which validates the agent's identity.

## 🚀 Key Features

### Property Listings
Agents can create and list properties with details like Price, Location, Bedrooms, and Area.
- **Endpoint**: `GET /properties` & `POST /properties`
- **Odoo View**: Sales -> Products -> Properties

### Inquiry Management
Potential buyers can submit inquiries that appear instantly in the Odoo CRM pipeline.
- **Endpoint**: `POST /inquiries`
- **Odoo View**: CRM -> Pipeline -> Leads

### Agent Dashboard
Real-time analytics fetched directly from Odoo.
- **Endpoint**: `GET /dashboard/stats`
- **Metrics**: Total Properties, Active Inquiries, and Agent Count.

## 🛠 Deployment & Setup

### Docker Configuration
The service is containerized using the **Astral UV** image for maximum performance.
```yaml
  realestate-api:
    image: ghcr.io/astral-sh/uv:python3.12-bookworm-slim
    ports:
      - "8003:8003"
    environment:
      - ODOO_URL=http://web:8069
```

### Seeding Data
The project includes a robust seeding engine (`seed_estate.py`) that populates the environment with:
- 5 Luxury Property listings.
- 3 Registered Real Estate Agents.
- 3 Active Customer Inquiries.

## 📈 Next Steps
- **Image Support**: Integrate Odoo's attachment system to handle property photos.
- **Map Integration**: Add Latitude/Longitude fields for property locations.
- **Customer Portal**: Expand the API to support a student/customer-facing property search interface.

---
*Documentation generated for Real Estate API v1.0*
