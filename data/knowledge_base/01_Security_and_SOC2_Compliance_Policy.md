# Document ID: SEC-POL-2026-V4
# Title: Enterprise Information Security, Privacy & SOC 2 Compliance Policy
# Effective Date: January 15, 2026
# Owner: Security & Compliance Engineering

## 1. Compliance Certifications & Frameworks
- **SOC 2 Type II:** Our platform maintains an active SOC 2 Type II attestation audited annually by an independent AICPA-certified firm covering Security, Availability, and Confidentiality trust service criteria.
- **GDPR & CCPA:** Fully compliant with EU General Data Protection Regulation (GDPR) and California Consumer Privacy Act (CCPA). Standard Contractual Clauses (SCCs) and a signed Data Processing Addendum (DPA) are available upon request.
- **HIPAA:** We support HIPAA-compliant workflows and sign Business Associate Agreements (BAAs) for Enterprise tier customers utilizing isolated tenant environments.
- **FedRAMP / ISO 27001:** We align with ISO 27001 controls (certification scheduled for Q4 2026). **Note:** We are NOT currently FedRAMP Authorized and do not support classified government cloud deployments.

## 2. Data Encryption Standards
- **Encryption at Rest:** All customer databases, vector embeddings (`pgvector`), object storage buckets, and automated backups are encrypted at rest using **AES-256** encryption with AWS KMS-managed keys rotated every 365 days.
- **Encryption in Transit:** All external API traffic, webhook payloads, and inter-service communications enforce **TLS 1.2 or TLS 1.3** with strong cipher suites. HTTP requests are automatically redirected to HTTPS with HSTS enabled.
- **Webhook Security:** All inbound and outbound webhooks require **HMAC-SHA256** cryptographic signature verification with a 300-second replay-protection timestamp window.

## 3. Access Control & Authentication
- **Single Sign-On (SSO):** SAML 2.0 and OIDC enterprise SSO (Okta, Azure AD / Entra ID, Google Workspace) are supported natively on Enterprise plans.
- **Multi-Factor Authentication (MFA):** Phishing-resistant MFA (FIDO2/WebAuthn or TOTP) is mandatory for 100% of internal engineering staff and enforced for all administrative customer accounts.
- **Role-Based Access Control (RBAC) & Tenant Isolation:** Multi-tenant data is strictly isolated at the database layer using PostgreSQL **Row-Level Security (RLS)** keyed by `organization_id`. Dedicated single-tenant VPC deployment is available only for contracts exceeding $100,000 ARR.

## 4. Data Retention, Deletion & AI Privacy (Zero Data Retention)
- **LLM Zero Data Retention (ZDR):** Customer prompts, documents, and CRM records sent to LLM providers (OpenAI Enterprise API, Google Vertex AI / Gemini API, Anthropic) are covered by commercial **Zero Data Retention (ZDR)** agreements. Customer data is **never** used to train foundation models.
- **Audit Log Retention:** Immutable security and webhook execution logs are retained in hot storage for **90 days** and cold encrypted archives for **365 days**.
- **Customer Data Deletion SLA:** Upon contract termination or written GDPR/CCPA erasure request, all primary customer data and vector embeddings are permanently purged from active databases within **30 calendar days** (and from encrypted backups within 60 days), followed by a formal Certificate of Destruction.

## 5. Vulnerability Management & Penetration Testing
- **External Penetration Testing:** Conducted **bi-annually (every 6 months)** by an independent CREST-certified third-party security firm. Executive summary reports are shared under NDA.
- **Automated Scanning:** Continuous SAST/DAST scanning via GitHub Advanced Security and Dependabot runs on every pull request. Critical vulnerabilities (CVSS >= 9.0) are patched within **24 hours**; High severity (CVSS 7.0–8.9) within **7 days**.

## 6. Approved Sub-Processors & Hosting Regions
- **Primary Cloud Infrastructure:** AWS (`us-east-1` N. Virginia primary, `eu-central-1` Frankfurt for EU data residency).
- **Database & Vector Store:** Supabase Enterprise (PostgreSQL 16 + `pgvector`).
- **On-Premise / Air-Gapped Deployments:** We operate strictly as a cloud-hosted SaaS/PaaS platform. We **do not** offer on-premise, self-hosted binary, or air-gapped installations.
