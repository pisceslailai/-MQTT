# Context Glossary

## Flow meter monitoring and retention system

A read-only system that collects, stores, displays, and alerts on flow meter readings. It does not remotely configure site devices and does not send control commands to field equipment.

## Device time

The timestamp reported by the gateway or field device. Device time is the business timestamp used for 15-minute windows.

## Receive time

The server timestamp captured when an MQTT message is received and stored. Receive time is audit evidence and is used to detect device clock drift.

## Raw reading

One standardized flow meter reading received through MQTT, including meter identity, device time, receive time, instant flow, cumulative flow, status, and the original payload.

## 15-minute settlement reading

A calculated record for one meter and one 15-minute device-time window. Usage is calculated from the cumulative flow difference inside the window.

## Data gap

A 15-minute window that does not contain enough valid raw readings to be treated as complete.

## Clock skew

A reading whose device time differs from server receive time by more than the configured threshold. The current threshold is 2 minutes.
