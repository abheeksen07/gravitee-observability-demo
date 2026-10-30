"""Generated AIAPI scenario; placement is illustrative, not discovered."""
import os
SERVICE = 'aiapi_api_gateway'
CLIENT = 'AIAPI-customer-applications'
BACKEND = 'AIAPI-customer-backend'
REDIS = 'AIAPI-rate-limit-redis'
MANAGEMENT = 'AIAPI-saas-management-api'
CONSOLE = 'AIAPI-management-console'
MONGO = 'AIAPI-mongodb-atlas'
KAFKA = 'AIAPI-confluent-cloud'
ELASTIC = 'AIAPI-elastic-cloud'
SES = 'AIAPI-aws-ses'
OVH = 'AIAPI-ovh-services'
SERVICES = (SERVICE, CLIENT, BACKEND, REDIS, MANAGEMENT, CONSOLE, MONGO, KAFKA, ELASTIC, SES, OVH)
AKS_SERVICES = (SERVICE, REDIS, MANAGEMENT, CONSOLE)
ROLES = dict(zip(SERVICES, ('gateway','caller','backend','rate-limiter','management','console','database','streaming','search','email','provider')))
# Illustrative application-tier topology; placement remains unspecified.
AUTH = 'AIAPI-auth-service'
ORDERS = 'AIAPI-order-service'
INVENTORY = 'AIAPI-inventory-service'
BILLING = 'AIAPI-billing-service'
PAYMENT = 'AIAPI-payment-gateway'
NOTIFICATION = 'AIAPI-notification-service'
APPLICATION_DEPENDENCIES = (AUTH, ORDERS, INVENTORY, BILLING, PAYMENT, NOTIFICATION)
SERVICES += APPLICATION_DEPENDENCIES
ROLES.update(dict(zip(APPLICATION_DEPENDENCIES, ('authentication','orders','inventory','billing','payments','notifications'))))
EXPANDED_TRACING = os.getenv('AIAPI_EXPANDED_TRACING', 'true').lower() == 'true'
TENANT = 'demo-sandbox.chronosphere.io'
OTLP_ENDPOINT = TENANT + ':443'
LOGS_ENDPOINT = 'https://' + TENANT + '/data/opentelemetry/v1/logs'
EVENTS_ENDPOINT = 'https://' + TENANT + '/api/v1/data/events'
METRIC_EXPORT_INTERVAL_SECONDS = 1
EXPORT_LENS_SPAN_METRICS = os.getenv('AIAPI_EXPORT_SPAN_METRICS', os.getenv('GRAVITEE_EXPORT_SPAN_METRICS', 'true')).lower() == 'true'
INCIDENT_REPEAT = os.getenv('AIAPI_REPEAT_INCIDENT', os.getenv('GRAVITEE_REPEAT_INCIDENT', 'false')).lower() == 'true'
ROUTES = ('GET /catalog/v1/products/{id}', 'POST /orders/v1/submissions', 'GET /accounts/v1/entitlements')
PROFILES = ('API product routing release with bundled gateway resource settings', 'Partner API policy release with bundled gateway resource settings', 'Order submission routing release with bundled gateway resource settings')
SOURCE_REPOSITORY = 'https://github.com/abheeksen07/gravitee-observability-demo'
SOURCE_REFERENCE = os.getenv('AIAPI_SOURCE_REF', os.getenv('GRAVITEE_SOURCE_REF', 'work'))

# Fixed generated account identifiers; no real customer identities.
ACCOUNTS = tuple(f'account-{i:03d}' for i in range(1,13))
