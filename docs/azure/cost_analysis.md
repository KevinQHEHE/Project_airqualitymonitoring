# **Azure Cost Analysis** 
**1. Actual System Configuration**

Virtual Machine Details

VM Name: aqm-vm

Location: Korea Central (Zone 1)

Size: Standard B1s (1 vCPU, 1 GiB RAM)

Operating System: Linux (Ubuntu 22.04)

VM Generation: V2

Architecture: x64

Image: Canonical Ubuntu Server (0001-com-ubuntu-server-jammy)

Networking Configuration

Public IP: 20.249.208.155

Private IP: 10.0.0.4

Virtual Network: aqm-vm-vnet/default

Network Interface: aqm-vm674\_z1

Storage & Security

Disk Type: SCSI

Security: Trusted Launch, Secure Boot Enabled, vTPM Enabled

Monitoring: Not enabled

Auto-shutdown: Not enabled

**2. Monthly Cost Breakdown**

**2.1. Virtual Machine (Current Configuration)**

|Service|Configuration|Monthly Cost (USD)|Annual Cost (USD)|
| :- | :- | :- | :- |
|VM Standard B1s|1 vCPU, 1GB RAM|$7.59|$91.08|
|OS Disk|30GB Standard SSD|$2.40|$28.80|
|Public IP Address|Static IPv4|$3.65|$43.80|
|Network Bandwidth|5GB outbound/month|$0.44|$5.28|
|Subtotal VM||$14.08|$168.96|

**2.2. Database & Storage**

|Service|Configuration|Monthly Cost (USD)|Annual Cost (USD)|
| :- | :- | :- | :- |
|MongoDB Atlas M0|Free Tier (512MB)|$0.00|$0.00|
|*or M10 if needed*|2GB RAM, 10GB storage|$57.00|$684.00|
|Azure Blob Storage|50GB Hot tier|$1.15|$13.80|
|Backup Storage|10GB LRS|$0.20|$2.40|
|Subtotal Storage|(with M0 Free)|$1.35|$16.20|
|Subtotal Storage|(with M10)|$58.35|$700.20|

**2.3. Monitoring & Management**

|Service|Configuration|Monthly Cost (USD)|Annual Cost (USD)|
| :- | :- | :- | :- |
|Application Insights|Basic (5GB data)|$0.00|$0.00|
|Azure Monitor|Basic metrics|$0.00|$0.00|
|Azure Key Vault|1000 operations|$3.00|$36.00|
|Subtotal Monitoring||$3.00|$36.00|

**3. Total Cost by Scenario**

Scenario 1: Development/Testing (Current Configuration + MongoDB Free)

|Category|Monthly Cost|Annual Cost|
| :- | :- | :- |
|Virtual Machine & Networking|$14.08|$168.96|
|Database & Storage|$1.35|$16.20|
|Monitoring & Management|$3.00|$36.00|
|TOTAL|$18.43|$221.16|

Scenario 2: Production (Current Configuration + MongoDB M10)

|Category|Monthly Cost|Annual Cost|
| :- | :- | :- |
|Virtual Machine & Networking|$14.08|$168.96|
|Database & Storage|$58.35|$700.20|
|Monitoring & Management|$3.00|$36.00|
|TOTAL|$75.43|$905.16|

Scenario 3: Production Upgrade (Standard B2s + MongoDB M10)

|Service|Configuration|Monthly Cost|Annual Cost|
| :- | :- | :- | :- |
|VM Standard B2s|2 vCPU, 4GB RAM|$30.37|$364.44|
|OS Disk|64GB Premium SSD|$9.60|$115.20|
|Public IP|Static IPv4|$3.65|$43.80|
|Network Bandwidth|15GB/month|$1.31|$15.72|
|MongoDB M10|2GB RAM, 10GB|$57.00|$684.00|
|Blob Storage|100GB Hot|$2.30|$27.60|
|Backup|20GB LRS|$0.40|$4.80|
|Key Vault|5000 ops/month|$5.00|$60.00|
|TOTAL||$109.63|$1,315.56|

