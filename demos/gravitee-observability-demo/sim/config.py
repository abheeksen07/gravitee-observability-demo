"""Generated Gravitee scenario; placement is illustrative, not discovered."""
import os
SERVICE = 'gravitee-api-gateway'
CLIENT = 'gravitee-customer-applications'
BACKEND = 'gravitee-customer-backend'
REDIS = 'gravitee-rate-limit-redis'
MANAGEMENT = 'gravitee-saas-management-api'
CONSOLE = 'gravitee-management-console'
MONGO = 'gravitee-mongodb-atlas'
KAFKA = 'gravitee-confluent-cloud'
ELASTIC = 'gravitee-elastic-cloud'
SES = 'gravitee-aws-ses'
OVH = 'gravitee-ovh-services'
SERVICES = (SERVICE, CLIENT, BACKEND, REDIS, MANAGEMENT, CONSOLE, MONGO, KAFKA, ELASTIC, SES, OVH)
AKS_SERVICES = (SERVICE, REDIS, MANAGEMENT, CONSOLE)
ROLES = dict(zip(SERVICES, ('gateway','caller','backend','rate-limiter','management','console','database','streaming','search','email','provider')))
TENANT = 'demo-sandbox.chronosphere.io'
OTLP_ENDPOINT = TENANT + ':443'
LOGS_ENDPOINT = 'https://' + TENANT + '/data/opentelemetry/v1/logs'
EVENTS_ENDPOINT = 'https://' + TENANT + '/api/v1/data/events'
METRIC_EXPORT_INTERVAL_SECONDS = 1
EXPORT_LENS_SPAN_METRICS = os.getenv('GRAVITEE_EXPORT_SPAN_METRICS', 'true').lower() == 'true'
INCIDENT_REPEAT = os.getenv('GRAVITEE_REPEAT_INCIDENT', 'false').lower() == 'true'
ROUTES = ('GET /catalog/v1/products/{id}', 'POST /orders/v1/submissions', 'GET /accounts/v1/entitlements')
PROFILES = ('API product routing release with bundled gateway resource settings', 'Partner API policy release with bundled gateway resource settings', 'Order submission routing release with bundled gateway resource settings')
SOURCE_REPOSITORY = 'https://github.com/abheeksen07/gravitee-observability-demo'
SOURCE_REFERENCE = os.getenv('GRAVITEE_SOURCE_REF', 'work')
