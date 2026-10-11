# Document ID: ARCH-SLA-2026-V2
# Title: System Architecture, Reliability, Disaster Recovery & SLA Specification
# Effective Date: February 1, 2026
# Owner: Platform & Site Reliability Engineering

## 1. Service Level Agreement (SLA) & Uptime Commitment
- **Guaranteed Uptime:** We guarantee **99.95% monthly uptime** across all core API endpoints, webhook ingestion gateways, and AI orchestration pipelines.
- **Scheduled Maintenance:** Maintenance windows are zero-downtime via blue/green deployments. Any rare disruptive maintenance requires 72 hours advance notice and occurs on Sundays between 02:00–04:00 UTC.
- **SLA Service Credits:**
  - 99.0% to < 99.95% monthly uptime: **10% service credit**
  - 95.0% to < 99.0% monthly uptime: **25% service credit**
  - Below 95.0% monthly uptime: **50% service credit**

## 2. Business Continuity & Disaster Recovery (BC/DR)
- **Recovery Time Objective (RTO):** **4 hours** maximum to restore full production service in the event of a catastrophic regional outage.
- **Recovery Point Objective (RPO):** **15 minutes** maximum data loss exposure, supported by continuous Point-in-Time Recovery (PITR) write-ahead log (WAL) streaming to a secondary AWS availability zone.
- **DR Testing Cadence:** Full failover and disaster recovery tabletop + live simulation drills are executed **every 6 months**.

## 3. Incident Response & Support Tiers
- **P1 — Critical (Production Down / Security Breach):**
  - First Response Time SLA: **<= 15 minutes** (24/7/365 PagerDuty escalation)
  - Update Frequency: Every 30 minutes until resolved
- **P2 — High (Major Feature Degraded / Webhook Latency Spike):**
  - First Response Time SLA: **<= 2 hours** (24/7 coverage)
  - Update Frequency: Every 4 hours
- **P3 — Medium (Non-Critical Bug / Minor Integration Issue):**
  - First Response Time SLA: **<= 8 business hours**
- **P4 — Low (General Question / Feature Request):**
  - First Response Time SLA: **<= 24 business hours**

## 4. Throughput, Rate Limits & Reliability Engineering
- **Webhook Ingestion Throughput:** Each tenant workspace supports a sustained rate limit of **500 requests per second (RPS)** and bursts up to **1,500 RPS** via our async Redis/FastAPI queue.
- **Dead-Letter Queue (DLQ) & Auto-Retry:** Failed downstream API deliveries (e.g., CRM outage or HTTP 429/5xx) are automatically retried up to **5 times** using exponential backoff with jitter (`2s, 4s, 8s, 16s, 32s`) before routing to a persistent Dead-Letter Queue (`DLQ`) with replay controls.
- **Idempotency Guarantee:** Every inbound event is deduplicated using a deterministic `idempotency_key` (`SHA-256` hash of source + event ID) stored with a 7-day TTL to guarantee zero duplicate CRM records.
