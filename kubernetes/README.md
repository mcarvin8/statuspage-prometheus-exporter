# Kubernetes Deployment Manifests

This directory contains generic Kubernetes manifests for deploying the StatusPage Prometheus Exporter.

## Files

- **namespace.yaml**: Creates the namespace for the exporter
- **configmap.yaml**: Contains the services.json configuration (update with your services)
- **persistentvolumeclaim.yaml**: Persistent volume for cache storage
- **deployment.yaml**: Main deployment manifest
- **service.yaml**: ClusterIP service for metrics endpoint
- **servicemonitor.yaml**: ServiceMonitor for Prometheus Operator (optional)

## Quick Start

1. **Update the ConfigMap** with your service configurations:
   ```bash
   # Edit kubernetes/configmap.yaml and add your services to services.json
   ```

2. **Customize the manifests** for your environment:
   - Update image references in `deployment.yaml`
   - Adjust resource limits/requests as needed
   - Update storage class in `persistentvolumeclaim.yaml` if needed
   - Add your organization-specific labels and annotations

3. **Deploy the manifests**:
   ```bash
   kubectl apply -f kubernetes/
   ```

## Configuration

### Environment Variables

The deployment supports the following environment variables (set in `deployment.yaml`):

- `CHECK_INTERVAL_MINUTES`: Interval in minutes between status checks (default: 20)
- `DEBUG`: Enable debug logging (set to `"true"` to enable)
- `CLEAR_CACHE`: Clear all cache files on startup (set to `"true"` to enable)
- `METRICS_PORT`: Prometheus metrics server port (default: 9001)
- `SERVICES_JSON_PATH`: Custom path to services.json (default: `/app/statuspage-exporter/services.json`)

### Storage

The exporter uses a PersistentVolumeClaim for cache storage. By default, it's configured for:
- **Size**: 100Mi
- **Access Mode**: ReadWriteOnce
- **Storage Class**: standard

If you're using NFS or need shared storage, change:
- `accessModes` to `ReadWriteMany`
- `storageClassName` to your NFS storage class

### Service Configuration

Update `configmap.yaml` with your actual service configurations. The format should match `services.json.example`:

```json
{
  "service_key": {
    "url": "https://status.example.com/api/v2/summary.json",
    "name": "Display Name"
  }
}
```

## Prometheus Integration

If you're using Prometheus Operator, the `servicemonitor.yaml` will automatically configure Prometheus to scrape the metrics endpoint.

Make sure your Prometheus Operator is configured to watch the namespace or add the appropriate label selector.

## Customization

### Adding Organization-Specific Labels/Annotations

Uncomment and update the annotations/labels sections in each manifest to match your organization's standards.

### Resource Limits

Adjust CPU and memory requests/limits in `deployment.yaml` based on:
- Number of services being monitored
- Check interval frequency
- Expected load

### Security Context

The manifests include basic security contexts. Adjust as needed for your security policies:
- `runAsNonRoot: true`
- `readOnlyRootFilesystem: false` (set to `true` if your security policy requires it, but ensure cache directory is writable)
- Capabilities dropped to minimum

## Troubleshooting

1. **Check pod logs**:
   ```bash
   kubectl logs -n statuspage-exporter deployment/statuspage-exporter
   ```

2. **Verify services.json is mounted correctly**:
   ```bash
   kubectl exec -n statuspage-exporter deployment/statuspage-exporter -- cat /app/statuspage-exporter/services.json
   ```

3. **Check metrics endpoint**:
   ```bash
   kubectl port-forward -n statuspage-exporter service/statuspage-exporter 9001:9001
   curl http://localhost:9001/metrics
   ```

4. **Verify cache persistence**:
   ```bash
   kubectl exec -n statuspage-exporter deployment/statuspage-exporter -- ls -la /app/statuspage-exporter/cache
   ```

