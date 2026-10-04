# Practical Linux & AWS Networking Engineering Notes

This document provides foundational and applied networking reference notes explaining how TCP/IP, DNS, HTTP, socket binding, and CIDR subnetting operate across the InfraOps platform.

---

## 1. TCP/IP Protocol & Socket Lifecycles

### 1.1 The TCP 3-Way Handshake
Transmission Control Protocol (TCP) establishes reliable, stateful bidirectional streams via a three-way handshake:
1. `SYN`: The client transmits a SYN segment containing an Initial Sequence Number (ISN) to initiate connection setup.
2. `SYN-ACK`: The server acknowledges receipt with an ACK matching client ISN + 1 and transmits its own SYN segment.
3. `ACK`: The client sends an ACK matching server ISN + 1, moving the socket into the `ESTABLISHED` state.

```
       Client                               Server (Port 8081)
         │                                         │
         │─────────────── SYN (seq=x) ────────────>│  (LISTEN)
         │                                         │
         │<───────── SYN-ACK (seq=y, ack=x+1) ─────│  (SYN_RECEIVED)
         │                                         │
         │────────────── ACK (ack=y+1) ───────────>│  (ESTABLISHED)
         │                                         │
```

### 1.2 Socket State Machine in L1 Troubleshooting
- `LISTEN`: The server daemon has bound to an IP/port and is actively waiting for incoming client connections.
- `ESTABLISHED`: An active, open data channel is exchanging frames.
- `TIME_WAIT`: The local endpoint initiated active close and is waiting 2 * Maximum Segment Lifetime (2MSL) to ensure lingering duplicate packets expire.
- `CLOSE_WAIT`: The remote end initiated closure; the local application has not yet closed its socket handle (often indicates an application file descriptor leak).

### 1.3 Troubleshooting Connection Failures
- `Connection Refused (ECONNREFUSED)`:
  The target host IP is reachable at Layer 3, but no process is actively bound and listening on the designated Layer 4 port.
  In InfraOps, this triggers when `demo_service` (port 8081) or `demo_upstream` (port 8082) is stopped.
- `Connection Timeout`:
  Packets are discarded silently without TCP RST responses, typically indicating firewall filtering, dead routing, or dropped packets.

---

## 2. Domain Name System (DNS) Architecture

### 2.1 Resolution Hierarchy
When an agent or service resolves a hostname:
1. Local File Check: Queries `/etc/hosts` for static name overrides.
2. Resolver Configuration: Reads `/etc/resolv.conf` for configured nameserver directives and search domains.
3. Recursive Lookup: If un-cached, queries recursive resolver (e.g. `127.0.0.1`, AmazonProvidedDNS at `VPC.2`, or public `1.1.1.1`).
4. Iterative Lookup: The recursive server navigates Root Nameservers (`.`), Top-Level Domain (TLD) servers, and authoritative nameservers.

### 2.2 Applied DNS Diagnostics in InfraOps
- SOP-005 handles DNS resolution failure.
- When an unreachable resolver is injected into the configuration, DNS queries block until the socket timeout.
- The `dns_diagnose` action probes each resolver in sequence, isolates the broken nameserver, and removes the fault flag to fall back to operational upstream resolvers.

---

## 3. HTTP & Service Availability Checks

### 3.1 Status Code Categorization
- `2xx Success`: Endpoint operational (e.g. `200 OK` on `/health`).
- `3xx Redirection`: Resource moved.
- `4xx Client Error`: Bad request (`400`), unauthorized (`401`), forbidden (`403`), or not found (`404`).
- `5xx Server Error`: Internal application crash (`500`), bad gateway (`502`), or service unavailable (`503`).

### 3.2 L1 Health Check Design Principles
- Health check endpoints (`/health`) should execute lightweight internal dependency checks.
- Health checks must include strict connection and read timeouts (e.g. 2-5 seconds) to prevent cascading thread starvation in the agent.

---

## 4. CIDR Subnetting & AWS 5-Reserved-IP Rules

### 4.1 CIDR Math Fundamentals
Classless Inter-Domain Routing (CIDR) expresses an IPv4 address block with a network prefix length (e.g. `10.0.0.0/16`).
The prefix length determines the number of bits allocated to the network portion, with the remaining `32 - prefix` bits allocated to host addressing.

- Total IP addresses: `2^(32 - prefix)`.
- Standard RFC 1122 usable hosts: `2^(32 - prefix) - 2` (subtracting the network address and broadcast address).

### 4.2 The AWS 5 Reserved IP Address Rule
In every AWS VPC subnet, Amazon Web Services reserves the first 4 IP addresses and the last IP address.
These addresses cannot be assigned to compute nodes or network interfaces.

| Offset | Address in `10.0.1.0/24` | Reserved Purpose in AWS |
|---|---|---|
| `+0` | `10.0.1.0` | **Network Address**: Identifies the subnet boundary. |
| `+1` | `10.0.1.1` | **VPC Router**: Default gateway for all outbound traffic. |
| `+2` | `10.0.1.2` | **AmazonProvidedDNS**: IP of the Amazon DNS / Route 53 Resolver. |
| `+3` | `10.0.1.3` | **Future Use**: Reserved by AWS for future platform capabilities. |
| `+255` | `10.0.1.255` | **Network Broadcast**: Standard broadcast address (broadcast is unsupported in VPC). |

### 4.3 Practical Host Capacity Calculation
For AWS subnets, usable host capacity is calculated as:
`AWS Usable Hosts = 2^(32 - prefix) - 5`

Examples across standard subnet sizes:
- `/16`: `65,536` total IPs -> `65,531` AWS usable hosts.
- `/20`: `4,096` total IPs -> `4,091` AWS usable hosts.
- `/24`: `256` total IPs -> `251` AWS usable hosts.
- `/28`: `16` total IPs -> `11` AWS usable hosts (smallest allowable subnet in AWS).
