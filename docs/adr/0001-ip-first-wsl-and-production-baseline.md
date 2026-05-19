# ADR 0001: Use IP-first deployment with minimum public-network safeguards

## Status

Accepted

## Context

The project needs a small monitoring system for two flow meters. The first milestone is to validate the MQTT-to-database-to-dashboard loop in WSL before renting and configuring a cloud server.

The planned production server will initially be accessed by public IP instead of a domain name. That keeps deployment simple, but makes normal browser HTTPS and MQTT TLS certificate management less straightforward.

## Decision

Use an IP-first deployment path:

- WSL validates the business loop first.
- Production initially uses public IP access.
- v1 does not require HTTPS or MQTT TLS.
- v1 must still use strong passwords, minimum exposed ports, Basic Auth for the web entry, and database backups.

## Consequences

This reduces initial setup work and avoids blocking the project on domain, filing, and certificate steps.

It also means v1 is not a high-security deployment. If the system becomes more sensitive or more widely accessed, the project should move to a domain-based HTTPS and MQTT TLS setup.
