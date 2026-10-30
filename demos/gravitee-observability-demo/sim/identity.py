from sim import config as C

def service_labels(service, instance=None):
    labels = {'demo':'AIAPI-api-platform', 'demo_build':'AIAPI-account-breakdown-v6', 'service': service, 'service_name': service, 'lens_service': service,
            'application': 'AIAPI-api-platform', 'team': 'api-platform',
            'environment': 'prod-us', 'service_role': C.ROLES[service],
            'instance': instance or service + '-0', 'az': 'us-placement-unvalidated'}
    if service in C.AKS_SERVICES:
        labels.update({'pod':labels['instance'], 'container':service,
                       'namespace':'AIAPI', 'cluster':'AIAPI-us-prod',
                       'node':'AIAPI-us-prod-node-'+('1' if labels['instance'].endswith('-1') else '0')})
    return labels

def resource_labels(service, instance=None):
    labels = service_labels(service, instance)
    labels.update({'service.name': service, 'service.instance.id': labels['instance'],
                   'service.namespace': 'AIAPI', 'deployment.environment.name': 'prod-us',
                   'placement.validation': 'illustrative; validate region and workload placement'})
    if service in C.AKS_SERVICES:
        labels.update({'cloud.provider': 'azure', 'cloud.platform': 'azure_aks',
                       'k8s.cluster.name': 'AIAPI-us-prod', 'k8s.namespace.name': 'AIAPI',
                       'k8s.node.name': labels['node'], 'k8s.pod.name': labels['instance'], 'k8s.deployment.name': service})
    # Managed dependencies and customer systems have unknown placement. No invented
    # Kubernetes/cloud/region metadata, and no manufactured on-premises equipment.
    return labels
