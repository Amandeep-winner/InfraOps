output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = aws_subnet.private[*].id
}

output "security_group_id" {
  description = "ID of the primary security group"
  value       = aws_security_group.infraops_sg.id
}

output "instance_ids" {
  description = "IDs of provisioned EC2 instances"
  value       = concat(aws_instance.web[*].id, [aws_instance.db.id])
}

output "s3_reports_bucket_name" {
  description = "Name of the incident reports archive S3 bucket"
  value       = aws_s3_bucket.incident_reports.id
}

output "s3_log_archive_bucket_name" {
  description = "Name of the log archive S3 bucket"
  value       = aws_s3_bucket.log_archive.id
}
