# Deployment Guide

This document covers deployment options for the Ollama-KIE.AI Proxy.

## Table of Contents

1. [Local Development](#local-development)
2. [Docker Deployment](#docker-deployment)
3. [Linux Systemd Service](#linux-systemd-service)
4. [Production Deployment](#production-deployment)
5. [Reverse Proxy Setup](#reverse-proxy-setup)

## Local Development

### macOS/Linux

```bash
# Install dependencies
make install

# Setup environment
make env-setup

# Edit .env with your KIE.AI API key
nano .env

# Start the service
make start

# In another terminal, test the service
make test-health
```

### Windows

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file
copy .env.example .env

# Edit .env with your KIE.AI API key
# Then run:
python -m uvicorn main:app --host 127.0.0.1 --port 11434 --reload
```

## Docker Deployment

### Quick Start with Docker Compose

1. **Create .env file:**
```bash
cp .env.example .env
# Edit .env with your KIE.AI API key
nano .env
```

2. **Start the service:**
```bash
docker-compose up -d
```

3. **View logs:**
```bash
docker-compose logs -f ollama-kie-proxy
```

4. **Stop the service:**
```bash
docker-compose down
```

### Build and Run Manually

```bash
# Build image
docker build -t ollama-kie-proxy:latest .

# Run container
docker run -d \
  --name ollama-kie-proxy \
  -p 11434:11434 \
  -e KIE_AI_API_KEY=your_api_key \
  -e KIE_AI_API_URL=https://api.kie.ai/v1 \
  -v /path/to/logs:/app/logs \
  ollama-kie-proxy:latest

# View logs
docker logs -f ollama-kie-proxy

# Stop container
docker stop ollama-kie-proxy
docker rm ollama-kie-proxy
```

### Docker Health Check

```bash
# Check if container is healthy
docker ps | grep ollama-kie-proxy

# View health status
docker inspect --format='{{.State.Health.Status}}' ollama-kie-proxy
```

## Linux Systemd Service

### Installation

1. **Copy service file:**
```bash
sudo cp ollama-kie-proxy.service /etc/systemd/system/
```

2. **Edit the service file to match your setup:**
```bash
sudo nano /etc/systemd/system/ollama-kie-proxy.service
```

Update:
- `User=` with your username
- `WorkingDirectory=` with your project path
- `EnvironmentFile=` with .env file path

3. **Reload systemd:**
```bash
sudo systemctl daemon-reload
```

4. **Start the service:**
```bash
sudo systemctl start ollama-kie-proxy
sudo systemctl enable ollama-kie-proxy  # Enable on boot
```

5. **Check status:**
```bash
sudo systemctl status ollama-kie-proxy
```

6. **View logs:**
```bash
sudo journalctl -u ollama-kie-proxy -f
```

7. **Stop the service:**
```bash
sudo systemctl stop ollama-kie-proxy
```

## Production Deployment

### Configuration Recommendations

1. **Use environment variables instead of .env:**
```bash
export KIE_AI_API_KEY=your_secure_key
export KIE_AI_API_URL=https://api.kie.ai/v1
export LOG_LEVEL=WARNING
export PROXY_HOST=0.0.0.0
export PROXY_PORT=11434
```

2. **Use a reverse proxy (Nginx):**

```nginx
upstream ollama_proxy {
    server 127.0.0.1:11434;
}

server {
    listen 443 ssl http2;
    server_name ollama.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://ollama_proxy;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }
}
```

3. **Enable rate limiting:**

```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;

location / {
    limit_req zone=api_limit burst=10;
    proxy_pass http://ollama_proxy;
}
```

### Docker Production Deployment

1. **Use multi-stage build for smaller images:**
```bash
docker build -t ollama-kie-proxy:prod . -f Dockerfile.prod
```

2. **Run with resource limits:**
```bash
docker run -d \
  --name ollama-kie-proxy \
  -p 11434:11434 \
  --memory="2g" \
  --cpus="2" \
  -e KIE_AI_API_KEY=your_api_key \
  -v /mnt/logs:/app/logs \
  --restart unless-stopped \
  ollama-kie-proxy:prod
```

3. **Use Docker Swarm for clustering:**
```bash
docker service create \
  --name ollama-kie-proxy \
  --publish 11434:11434 \
  --replicas 3 \
  --env KIE_AI_API_KEY=your_api_key \
  ollama-kie-proxy:prod
```

### Kubernetes Deployment

Create `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama-kie-proxy
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ollama-kie-proxy
  template:
    metadata:
      labels:
        app: ollama-kie-proxy
    spec:
      containers:
      - name: proxy
        image: ollama-kie-proxy:latest
        ports:
        - containerPort: 11434
        env:
        - name: KIE_AI_API_KEY
          valueFrom:
            secretKeyRef:
              name: kie-secrets
              key: api-key
        - name: KIE_AI_API_URL
          value: "https://api.kie.ai/v1"
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1"
        livenessProbe:
          httpGet:
            path: /health
            port: 11434
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 11434
          initialDelaySeconds: 5
          periodSeconds: 10
        volumeMounts:
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: logs
        emptyDir: {}

---
apiVersion: v1
kind: Service
metadata:
  name: ollama-kie-proxy-service
spec:
  type: LoadBalancer
  ports:
  - port: 11434
    targetPort: 11434
  selector:
    app: ollama-kie-proxy
```

Deploy:
```bash
kubectl apply -f deployment.yaml
kubectl create secret generic kie-secrets --from-literal=api-key=YOUR_API_KEY
```

## Reverse Proxy Setup

### Nginx with HTTPS

```bash
# Create SSL certificate (self-signed for testing)
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365

# Install Nginx
# macOS: brew install nginx
# Ubuntu: sudo apt-get install nginx

# Create Nginx config
sudo tee /etc/nginx/sites-available/ollama-proxy > /dev/null <<EOF
upstream ollama_backend {
    server 127.0.0.1:11434;
}

server {
    listen 80;
    server_name localhost;
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl;
    server_name localhost;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://ollama_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
EOF

# Enable the site
sudo ln -s /etc/nginx/sites-available/ollama-proxy /etc/nginx/sites-enabled/

# Test and restart
sudo nginx -t
sudo systemctl restart nginx
```

### Apache with HTTPS

```apache
<VirtualHost *:443>
    ServerName ollama.example.com
    
    SSLEngine on
    SSLCertificateFile /path/to/cert.pem
    SSLCertificateKeyFile /path/to/key.pem
    
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:11434/
    ProxyPassReverse / http://127.0.0.1:11434/
    
    # WebSocket support
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/?(.*) "http://127.0.0.1:11434/$1" [P,L]
</VirtualHost>

<VirtualHost *:80>
    ServerName ollama.example.com
    Redirect permanent / https://ollama.example.com/
</VirtualHost>
```

## Monitoring and Logging

### Application Logs

```bash
# View all logs
make logs

# View error logs
make logs-errors

# View request logs
make logs-requests

# Follow logs in real-time
tail -f logs/*.log
```

### Health Monitoring

```bash
# Check service status
curl http://127.0.0.1:11434/health

# Monitor continuously
watch -n 5 'curl -s http://127.0.0.1:11434/health'
```

### Log Aggregation (Optional)

For production, consider using:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Splunk
- Datadog
- New Relic

Configure application to forward logs to these services.

## Security Checklist

- [ ] API key stored in environment variables, not in code
- [ ] HTTPS/SSL enabled for production
- [ ] Rate limiting configured
- [ ] Firewall rules restrict access
- [ ] Regular security updates applied
- [ ] Logs monitored for suspicious activity
- [ ] Database credentials (if any) rotated regularly
- [ ] Application runs with minimal privileges
- [ ] Request/response logs reviewed periodically

## Performance Tuning

### Uvicorn Workers

```bash
# For CPU-bound workloads
python -m uvicorn main:app --workers $(nproc) --port 11434

# For I/O-bound workloads (async)
python -m uvicorn main:app --workers 4 --port 11434
```

### Connection Pooling

Configure in `config.py`:
```python
pool_connections = 100
pool_maxsize = 100
timeout = 60.0
```

### Caching

For production, consider adding:
- Redis for response caching
- CDN for static content

## Backup and Recovery

### Backup Logs

```bash
# Daily backup
0 2 * * * tar -czf /backup/logs-$(date +\%Y\%m\%d).tar.gz /path/to/logs/
```

### Database Backup (if using)

```bash
# PostgreSQL example
pg_dump dbname | gzip > /backup/db-$(date +%Y%m%d).sql.gz
```

## Support and Troubleshooting

For issues:
1. Check logs: `make logs`
2. Test health: `curl http://localhost:11434/health`
3. Review error logs: `make logs-errors`
4. Check KIE.AI API status
5. Verify network connectivity
