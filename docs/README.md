# FarmIQ Documentation

**Last Updated**: 2026-07-14

Welcome to the FarmIQ platform documentation. This directory contains comprehensive documentation for all layers of the system.

## 🚀 Quick Start

- **New to FarmIQ?** Start with [Start Here](00-START-HERE.md)
- Architecture overview: [01-architecture.md](01-architecture.md)
- **Service Status** → [STATUS.md](STATUS.md)
- **API Contracts** → [contracts/](contracts/)
- **Progress Tracking** → [progress/](progress/)

## 📋 Recent Updates

### 2026-07-13
- IoT-layer WeighVision post-deployment enhancement plan added
  - Weight estimation validation
  - Metadata pipeline verification
  - YOLO26 upgrade planning
  - AI weight prediction readiness
  - See: [iot-layer/04-field-deployment-enhancement-plan.md](iot-layer/04-field-deployment-enhancement-plan.md)
- IoT-layer WeighVision ticket backlog added
  - Epic and ticket breakdown
  - Agent Skill / Agent Role mapping
  - Dependency map and first-sprint recommendation
  - See: [iot-layer/05-field-deployment-ticket-backlog.md](iot-layer/05-field-deployment-ticket-backlog.md)
- IoT-layer WeighVision work orders added
  - One Work Order file per ticket
  - Ready for assignment and execution tracking
  - See: [iot-layer/work-orders/README.md](iot-layer/work-orders/README.md)

### 2026-07-14
- WeighVision Batch 1 metadata traceability hardening added
  - Canonical metadata contract
  - Edge raw metadata persistence and normalized feature mapping
  - Metadata verification pack and SQL query pack
  - See: [contracts/weighvision-capture-metadata.contract.md](contracts/weighvision-capture-metadata.contract.md)
  - See: [iot-layer/06-metadata-verification-pack.md](iot-layer/06-metadata-verification-pack.md)
- WeighVision local rebuild and smoke verification runbook added
  - Standard `rebuild + up + smoke verify` commands
  - Covers Edge and Cloud local traceability path
  - See: [iot-layer/07-local-traceability-runbook.md](iot-layer/07-local-traceability-runbook.md)
- WeighVision Batch 1 exit gate validated locally
  - one session verified from `JSON -> Edge -> Cloud`
  - evidence session: `sess-int-20260714-004`
  - See: [iot-layer/06-metadata-verification-pack.md](iot-layer/06-metadata-verification-pack.md)
- WeighVision Batch 2 root-cause audit pack added
  - field audit dataset generator and evidence outputs
  - final-weight path reconstruction and anomaly categorization
  - baseline parameter recommendation for next field rerun
  - See: [iot-layer/08-weight-estimation-audit-pack.md](iot-layer/08-weight-estimation-audit-pack.md)
- WeighVision Batch 2.1 final-weight local smoke proof added
  - Docker Compose rebuild and verification runbook
  - Edge + Cloud SQL checklist for `final_weight_kg`
  - evidence of the passing end-to-end session and the Cloud readmodel defects fixed during proof
  - See: [iot-layer/09-final-weight-local-smoke-runbook.md](iot-layer/09-final-weight-local-smoke-runbook.md)
- WeighVision Batch 4 Cloud-Edge AI control-plane MVP added
  - Cloud dataset contract, model registry, and subscription APIs
  - Edge subscription cache and manifest-based activation or fallback metadata handling
  - local verification evidence for Cloud API tests, Edge tests, Docker Compose smoke, and TypeScript builds
  - See: [contracts/weighvision-model-control-plane.contract.md](contracts/weighvision-model-control-plane.contract.md)
  - See: [iot-layer/12-cloud-edge-ai-control-plane-pack.md](iot-layer/12-cloud-edge-ai-control-plane-pack.md)
- WeighVision Batch 4 rerun runbook added
  - Standard `build + up -d + unit + smoke` commands
  - Smoke checkpoints and known fixed defect list included
  - See: [iot-layer/13-cloud-edge-ai-control-plane-runbook.md](iot-layer/13-cloud-edge-ai-control-plane-runbook.md)

### 2025-12-27
- ✅ **Notifications (in-app, MVP)** - end-to-end wiring documented and implemented
  - Notification service `/api/v1/notifications/{send,inbox,history}`
  - BFF proxy + dashboard alias routes
  - Dashboard-web bell + notifications page
  - Evidence: `docs/evidence/NOTIFICATIONS_EVIDENCE.md`
  - Progress: `docs/progress/dashboard-web-notifications.md`

- ✅ **Architecture Diagram** - Premium visual diagram created
  - Cloud, Edge, and IoT layers
  - Service dependencies and data flow
  - See: [farmiq_architecture_diagram_1766843322006.png](farmiq_architecture_diagram_1766843322006.png)

## 📚 Documentation Structure

### Core Documentation
- [00-START-HERE.md](00-START-HERE.md) - Read first (how to run + key links)
- [00-index.md](00-index.md) - Detailed documentation index
- [01-architecture.md](01-architecture.md) - System architecture
- [STATUS.md](STATUS.md) - Service status and progress tracking
- [WORKFLOW.md](WORKFLOW.md) - Development workflow
- [ROUTES.md](ROUTES.md) - API routes catalog
  - Roadmap: [ROADMAP.md](ROADMAP.md)
  - Decisions: [DECISIONS.md](DECISIONS.md)

### Layer-Specific Documentation
- [cloud-layer/](cloud-layer/) - Cloud services documentation
- [edge-layer/](edge-layer/) - Edge services documentation
- [iot-layer/](iot-layer/) - IoT layer documentation

### Contracts & APIs
- [contracts/](contracts/) - Service contracts and interfaces
- [shared/](shared/) - Shared schemas and OpenAPI specs

### Progress & Evidence
- [progress/](progress/) - Detailed progress tracking (37+ files)
- [evidence/](evidence/) - Test evidence and verification

### Compliance & Audits
- [compliance/](compliance/) - Compliance documentation
- [audits/](audits/) - Audit reports

## 🔍 Finding Information

### By Topic

**Architecture & Design**
- System overview: [01-architecture.md](01-architecture.md)
- Data model: [02-domain-multi-tenant-data-model.md](02-domain-multi-tenant-data-model.md)
- Database design: [04-database-design.md](04-database-design.md)
- Messaging: [03-messaging-rabbitmq.md](03-messaging-rabbitmq.md)

**Security & Access**
- RBAC: [06-rbac-authorization-matrix.md](06-rbac-authorization-matrix.md)
- Backup & DR: [07-backup-dr-plan.md](07-backup-dr-plan.md)

**Operations**
- Alerts & SLOs: [08-alerts-slos.md](08-alerts-slos.md)
- Service status: [STATUS.md](STATUS.md)

**Development**
- Workflow: [WORKFLOW.md](WORKFLOW.md)
- Dev guides: [dev/](dev/)

### By Service

All service-specific documentation is in [progress/](progress/):
- Cloud services: `cloud-*.md`
- Edge services: `edge-*.md`
- Dashboard: `dashboard-web*.md`

### By Feature

**Notifications**
- Progress: [progress/dashboard-web-notifications.md](progress/dashboard-web-notifications.md)
- Evidence: [evidence/NOTIFICATIONS_EVIDENCE.md](evidence/NOTIFICATIONS_EVIDENCE.md)
- Implementation: [../apps/dashboard-web/NOTIFICATIONS_IMPLEMENTATION.md](../apps/dashboard-web/NOTIFICATIONS_IMPLEMENTATION.md)

**Feeding Module**
- Service: [progress/cloud-feed-service.md](progress/cloud-feed-service.md)
- Dashboard: [progress/dashboard-web.md](progress/dashboard-web.md)

**WeighVision**
- Read model: [progress/cloud-weighvision-readmodel.md](progress/cloud-weighvision-readmodel.md)
- Dashboard: [progress/dashboard-web.md](progress/dashboard-web.md)
- Enhancement plan: [iot-layer/04-field-deployment-enhancement-plan.md](iot-layer/04-field-deployment-enhancement-plan.md)
- Ticket backlog: [iot-layer/05-field-deployment-ticket-backlog.md](iot-layer/05-field-deployment-ticket-backlog.md)
- Metadata verification pack: [iot-layer/06-metadata-verification-pack.md](iot-layer/06-metadata-verification-pack.md)
- Weight estimation audit pack: [iot-layer/08-weight-estimation-audit-pack.md](iot-layer/08-weight-estimation-audit-pack.md)
- Final-weight local smoke runbook: [iot-layer/09-final-weight-local-smoke-runbook.md](iot-layer/09-final-weight-local-smoke-runbook.md)
- Cloud-Edge AI control-plane pack: [iot-layer/12-cloud-edge-ai-control-plane-pack.md](iot-layer/12-cloud-edge-ai-control-plane-pack.md)
- Cloud-Edge AI control-plane runbook: [iot-layer/13-cloud-edge-ai-control-plane-runbook.md](iot-layer/13-cloud-edge-ai-control-plane-runbook.md)
- Work orders: [iot-layer/work-orders/README.md](iot-layer/work-orders/README.md)

## 📊 Service Status

See [STATUS.md](STATUS.md) for complete service status, including:
- Service list with ports and health status
- Definition of Done criteria
- Detailed TODO checklists
- Integration status

**Quick Stats** (as of 2025-12-27):
- Cloud services: 15+ services
- Edge services: 10+ services
- Dashboard: 40+ pages
- Status: Most services complete, dashboard in active development

## 🏗️ Architecture Diagrams

- **Main Architecture**: [FarmIQ-Architecture.png](FarmIQ-Architecture.png)
- **Premium Diagram**: [farmiq_architecture_diagram_1766843322006.png](farmiq_architecture_diagram_1766843322006.png)

## 🔗 External Resources

- **API Gateway (BFF)**: `http://localhost:5125/api-docs`
- **Dashboard Web**: `http://localhost:5142`
- **Docker Compose (cloud-layer)**: `cloud-layer/docker-compose.yml` + `cloud-layer/docker-compose.dev.yml`

## 📝 Contributing to Documentation

When updating documentation:
1. Update [STATUS.md](STATUS.md) for service status changes
2. Create/update progress docs in [progress/](progress/)
3. Add evidence to [evidence/](evidence/)
4. Update this README if adding new major sections
5. Keep the "Last Updated" date current

## 🆘 Need Help?

- Check [00-index.md](00-index.md) for detailed index
- Review [WORKFLOW.md](WORKFLOW.md) for development process
- See service-specific docs in [progress/](progress/)
- Check [STATUS.md](STATUS.md) for current implementation status
