# AWS IoT Core Setup Instructions

This guide walks you through setting up AWS IoT Core for the Smart Agriculture Monitoring System.

## Prerequisites

- AWS Account with IoT Core access
- AWS CLI installed and configured
- Python 3.8+ with boto3 installed

---

## Step 1: Create an IoT Thing

### Using AWS Console

1. Go to **AWS IoT Core** → **Manage** → **All devices** → **Things**
2. Click **Create things**
3. Select **Create single thing**, click **Next**
4. Enter Thing name: `farm-sensor-001`
5. Under Thing type, create or select `AgricultureSensor`
6. Click **Next** and continue to certificate creation

### Using AWS CLI

```bash
# Create thing type (optional but recommended)
aws iot create-thing-type \
    --thing-type-name AgricultureSensor \
    --thing-type-properties "thingTypeDescription=Agricultural monitoring sensors"

# Create the thing
aws iot create-thing \
    --thing-name farm-sensor-001 \
    --thing-type-name AgricultureSensor \
    --attribute-payload "attributes={location=Field-A,sensorType=DHT22+SoilMoisture}"
```

---

## Step 2: Create and Download Certificates

### Using AWS Console

1. After creating the thing, select **Auto-generate a new certificate**
2. Click **Next**
3. Download all certificate files:
   - `XXXXXXXXXX-certificate.pem.crt` → Rename to `device-certificate.pem.crt`
   - `XXXXXXXXXX-private.pem.key` → Rename to `device-private.pem.key`
   - `XXXXXXXXXX-public.pem.key` (optional backup)
4. Download **Amazon Root CA 1** from the provided link → Save as `AmazonRootCA1.pem`
5. Click **Activate** to activate the certificate
6. Click **Attach a policy** (we'll create one next)

### Using AWS CLI

```bash
# Create certificate
aws iot create-keys-and-certificate \
    --set-as-active \
    --certificate-pem-outfile certs/device-certificate.pem.crt \
    --public-key-outfile certs/device-public.pem.key \
    --private-key-outfile certs/device-private.pem.key

# Download Amazon Root CA
curl -o certs/AmazonRootCA1.pem https://www.amazontrust.com/repository/AmazonRootCA1.pem
```

---

## Step 3: Create IoT Policy

### Using AWS Console

1. Go to **AWS IoT Core** → **Security** → **Policies**
2. Click **Create policy**
3. Name: `AgricultureSensorPolicy`
4. Click **JSON** tab and paste contents from `aws/iot-policy.json`
5. Click **Create**

### Using AWS CLI

```bash
# Create policy from file
aws iot create-policy \
    --policy-name AgricultureSensorPolicy \
    --policy-document file://aws/iot-policy.json
```

---

## Step 4: Attach Policy to Certificate

### Using AWS Console

1. Go to **AWS IoT Core** → **Security** → **Certificates**
2. Click on your certificate
3. Click **Actions** → **Attach policy**
4. Select `AgricultureSensorPolicy`
5. Click **Attach**

### Using AWS CLI

```bash
# Get certificate ARN (from create-keys-and-certificate output)
CERT_ARN="arn:aws:iot:REGION:ACCOUNT_ID:cert/CERTIFICATE_ID"

# Attach policy
aws iot attach-policy \
    --policy-name AgricultureSensorPolicy \
    --target $CERT_ARN
```

---

## Step 5: Attach Certificate to Thing

### Using AWS Console

1. Go to **AWS IoT Core** → **Manage** → **Things** → `farm-sensor-001`
2. Click **Certificates** tab
3. Click **Attach certificate**
4. Select your certificate
5. Click **Attach**

### Using AWS CLI

```bash
# Attach certificate to thing
aws iot attach-thing-principal \
    --thing-name farm-sensor-001 \
    --principal $CERT_ARN
```

---

## Step 6: Get IoT Endpoint

### Using AWS Console

1. Go to **AWS IoT Core** → **Settings**
2. Copy the **Device data endpoint** (e.g., `xxxxx-ats.iot.us-east-1.amazonaws.com`)

### Using AWS CLI

```bash
aws iot describe-endpoint --endpoint-type iot:Data-ATS
```

---

## Step 7: Update Configuration

1. Copy certificates to `certs/` directory:
   ```
   certs/
   ├── AmazonRootCA1.pem
   ├── device-certificate.pem.crt
   └── device-private.pem.key
   ```

2. Update `config/config.yaml`:
   ```yaml
   aws_iot:
     endpoint: "YOUR_ENDPOINT.iot.YOUR_REGION.amazonaws.com"
     region: "YOUR_REGION"
   ```

---

## Step 8: Create IoT Rule for Alerts

### Using AWS Console

1. Go to **AWS IoT Core** → **Message routing** → **Rules**
2. Click **Create rule**
3. Rule name: `AgricultureAlertRule`
4. SQL statement:
   ```sql
   SELECT * FROM 'agriculture/sensors/+/alerts' 
   WHERE severity = 'critical' OR severity = 'warning'
   ```
5. Add actions:
   - **SNS**: Send to an SNS topic
   - **CloudWatch Logs**: Log to `/aws/iot/agriculture-alerts`
6. Click **Create**

---

## Step 9: Create SNS Topic for Alerts

```bash
# Create SNS topic
aws sns create-topic --name AgricultureAlerts

# Subscribe email to topic
aws sns subscribe \
    --topic-arn arn:aws:sns:REGION:ACCOUNT_ID:AgricultureAlerts \
    --protocol email \
    --notification-endpoint your-email@example.com
```

---

## Step 10: Create CloudWatch Dashboard

### Using AWS Console

1. Go to **CloudWatch** → **Dashboards**
2. Click **Create dashboard**
3. Name: `SmartAgricultureDashboard`
4. Click **Actions** → **View/edit source**
5. Paste contents from `aws/cloudwatch-dashboard.json`
6. Update `DeviceId` values to match your device
7. Click **Update**

### Using AWS CLI

```bash
aws cloudwatch put-dashboard \
    --dashboard-name SmartAgricultureDashboard \
    --dashboard-body file://aws/cloudwatch-dashboard.json
```

---

## Step 11: Test Connection

```bash
# Navigate to project directory
cd d:\UVM\PROJECTS\Smart-Agricultural-Monitoring-System

# Test connection
python -m scripts.main --test-connection
```

Expected output:
```
Testing AWS IoT connection...
✓ AWS IoT Core connection successful!
```

---

## Step 12: Run in Simulation Mode

```bash
# Run with simulated sensors
python -m scripts.main --simulate --duration 60
```

---

## Troubleshooting

### Connection Timeout

- Verify endpoint URL in `config/config.yaml`
- Check security group allows outbound MQTT (port 8883)
- Ensure certificate is activated

### Certificate Error

- Verify all three files are in `certs/` directory
- Check file permissions (readable by Python)
- Ensure certificate is attached to policy and thing

### Policy Denied

- Verify policy allows the topics being used
- Check thing name matches policy variables
- Review CloudWatch Logs for detailed errors

---

## Security Best Practices

1. **Never commit certificates** to version control
2. Use separate certificates per device
3. Rotate certificates periodically
4. Use least-privilege policies
5. Enable CloudWatch logging for audit
