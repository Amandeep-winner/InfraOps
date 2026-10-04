# ==============================================================================
# InfraOps Infrastructure as Code (Terraform Specification)
#
# NOTE: This Terraform configuration serves as the declarative reference architecture
# for InfraOps AWS infrastructure (VPC, subnets, EC2, IAM, S3, CloudWatch).
# In accordance with project requirements, this configuration is offline-tested and
# validated, but is not applied against live cloud resources in local test runs.
# ==============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "InfraOps"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# -----------------------------------------------------------------------------
# 1. Networking: VPC, Internet Gateway, Subnets, and Route Tables
# -----------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "infraops-vpc"
  }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "infraops-igw"
  }
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "infraops-public-${count.index + 1}"
    Type = "public"
  }
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "infraops-private-${count.index + 1}"
    Type = "private"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = {
    Name = "infraops-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(var.public_subnet_cidrs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# -----------------------------------------------------------------------------
# 2. Security Groups
# -----------------------------------------------------------------------------

resource "aws_security_group" "infraops_sg" {
  name        = "infraops-sg"
  description = "InfraOps workload security group with least-privilege ingress"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH from authorized bastion/admin only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  ingress {
    description = "Ingest API access within VPC CIDR"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  ingress {
    description = "HTTPS public ingress"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Outbound internet access for packages and updates"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "infraops-sg"
  }
}

# -----------------------------------------------------------------------------
# 3. IAM Role, Policies, and Instance Profile
# -----------------------------------------------------------------------------

resource "aws_iam_role" "agent_role" {
  name = "infraops-agent-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action    = "sts:AssumeRole"
        Effect    = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "infraops-agent-role"
  }
}

resource "aws_iam_policy" "agent_policy" {
  name        = "InfraOpsAgentLeastPrivilegePolicy"
  description = "Scoped policy for CloudWatch telemetry and S3 incident reports"
  policy      = file("${path.module}/iam_policies/agent_policy.json")
}

resource "aws_iam_role_policy_attachment" "agent_attach" {
  role       = aws_iam_role.agent_role.name
  policy_arn = aws_iam_policy.agent_policy.arn
}

resource "aws_iam_instance_profile" "agent_profile" {
  name = "infraops-agent-profile"
  role = aws_iam_role.agent_role.name
}

# -----------------------------------------------------------------------------
# 4. Compute: EC2 Instances
# -----------------------------------------------------------------------------

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "web" {
  count                = 2
  ami                  = data.aws_ami.amazon_linux_2023.id
  instance_type        = var.instance_type
  subnet_id            = aws_subnet.public[count.index].id
  vpc_security_group_ids = [aws_security_group.infraops_sg.id]
  iam_instance_profile = aws_iam_instance_profile.agent_profile.name

  user_data = <<-EOF
              #!/bin/bash
              set -euo pipefail
              echo "Bootstrapping InfraOps Web Node..."
              EOF

  tags = {
    Name = "infraops-web-${count.index + 1}"
    Tier = "web"
  }
}

resource "aws_instance" "db" {
  ami                  = data.aws_ami.amazon_linux_2023.id
  instance_type        = var.instance_type
  subnet_id            = aws_subnet.private[0].id
  vpc_security_group_ids = [aws_security_group.infraops_sg.id]
  iam_instance_profile = aws_iam_instance_profile.agent_profile.name

  tags = {
    Name = "infraops-db-1"
    Tier = "db"
  }
}

# -----------------------------------------------------------------------------
# 5. Storage: S3 Buckets with Encryption, Versioning, and Public Access Block
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "incident_reports" {
  bucket        = "infraops-incident-reports"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "incident_reports" {
  bucket = aws_s3_bucket.incident_reports.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "incident_reports" {
  bucket = aws_s3_bucket.incident_reports.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "log_archive" {
  bucket        = "infraops-log-archive"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "log_archive" {
  bucket = aws_s3_bucket.log_archive.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "log_archive" {
  bucket = aws_s3_bucket.log_archive.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# -----------------------------------------------------------------------------
# 6. Monitoring: CloudWatch Log Group and Metric Alarms
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "infraops_logs" {
  name              = "/infraops/hosts"
  retention_in_days = 30
}

resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "HighCPUAlarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUPercent"
  namespace           = "InfraOps/Host"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Alarm when average host CPU exceeds 80%"
}

resource "aws_cloudwatch_metric_alarm" "high_memory" {
  alarm_name          = "HighMemoryAlarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemPercent"
  namespace           = "InfraOps/Host"
  period              = 60
  statistic           = "Average"
  threshold           = 85
  alarm_description   = "Alarm when average host memory exceeds 85%"
}

resource "aws_cloudwatch_metric_alarm" "disk_space" {
  alarm_name          = "DiskSpaceAlarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DiskPercent"
  namespace           = "InfraOps/Host"
  period              = 60
  statistic           = "Average"
  threshold           = 90
  alarm_description   = "Alarm when host disk usage exceeds 90%"
}
